"""
Campaign API — list, launch, activate/pause, copy-suggest, status sync.

Phase A.5 (hackathon UI): single-tenant founder account via env credentials,
but every route is auth-gated and ownership-scoped so the Phase B multi-tenant
swap only touches the token-resolution layer.
"""
import os
import secrets
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from backend.dependencies import get_current_user
from backend.logger import get_logger
from backend.services.ads_service.ai_copy import generate_ad_copy_variants
from backend.services.ads_service.base import MAX_COPY_VARIANTS, get_ad_entries
from backend.services.ads_service.cost import charge_ad_launch
from backend.services.ads_service.launcher import get_founder_platform, run_launch
from backend.services.db_service import ads_db, new_launch_id
from backend.services.sync_service import sync_launch

logger = get_logger(__name__)
router = APIRouter()


class CopyVariant(BaseModel):
    primary_text: str
    headline: str
    description: str = ""


class LaunchRequest(BaseModel):
    run_id: Optional[str] = None
    video_url: Optional[str] = None
    daily_budget_cents: int = Field(gt=0)
    landing_url: str
    objective: str = "OUTCOME_TRAFFIC"
    cta_type: str = "LEARN_MORE"
    countries: list[str] = ["IN"]
    age_min: int = 18
    age_max: int = 65
    name: Optional[str] = None
    # A/B test: 1-3 copy variants, one ad each. The singular fields below are
    # the pre-variant API shape — still accepted as a one-variant launch.
    variants: Optional[list[CopyVariant]] = Field(default=None, max_length=MAX_COPY_VARIANTS)
    primary_text: Optional[str] = None
    headline: Optional[str] = None
    description: str = ""
    ai_generated: bool = False


class CopySuggestRequest(BaseModel):
    run_id: Optional[str] = None
    landing_url: str
    product_hint: str = ""
    num_variants: int = Field(default=1, ge=1, le=MAX_COPY_VARIANTS)


class ConfirmBody(BaseModel):
    confirm: bool = False


def require_launch_access(user: dict = Depends(get_current_user)) -> dict:
    """Private beta: launching/operating ads is allowlisted. Phase A runs on
    the founder's Meta ad account via env credentials, so an open /launch
    would let ANY signed-in Google user create campaigns on that account.
    Allowlist via ADS_ALLOWED_USER_IDS (comma-separated), default founder."""
    allowed = os.getenv("ADS_ALLOWED_USER_IDS") or os.getenv("FOUNDER_USER_ID", "")
    allowed_ids = {uid.strip() for uid in allowed.split(",") if uid.strip()}
    if user["uid"] not in allowed_ids:
        raise HTTPException(status_code=403,
                            detail="IgniteAds is in private beta — launching is not enabled "
                                   "for this account yet. Reach out via igniteai.in.")
    return user


def _own_launch_or_404(launch_id: str, user_id: str) -> dict:
    launch = ads_db.get_ad_launch(launch_id)
    if not launch or launch.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Launch not found")
    return launch


def require_task_auth(x_task_auth: Optional[str] = Header(None)) -> None:
    """Gate for machine endpoints (Cloud Tasks / Cloud Scheduler): the caller
    must present the shared ADS_TASK_AUTH_TOKEN. When the env var is unset the
    gate is open (local dev / first rollout) — loudly, so it gets set."""
    expected = os.getenv("ADS_TASK_AUTH_TOKEN", "")
    if not expected:
        logger.warning("ADS_TASK_AUTH_TOKEN unset — task endpoints are UNGATED; "
                       "set it in .config/cloud-run-env.yaml and redeploy")
        return
    if not x_task_auth or not secrets.compare_digest(x_task_auth, expected):
        raise HTTPException(status_code=403, detail="Bad or missing X-Task-Auth")


@router.get("/runs")
async def list_completed_runs(user: dict = Depends(get_current_user)):
    """Completed IgniteAI runs (videos available to launch)."""
    from google.cloud.firestore_v1.base_query import FieldFilter
    docs = ads_db.db.collection("executions") \
        .where(filter=FieldFilter("user_id", "==", user["uid"])).stream()
    runs = []
    for d in docs:
        r = d.to_dict()
        url = (r.get("result") or {}).get("video_url")
        if r.get("status") == "completed" and url:
            runs.append({
                "run_id": d.id,
                "video_url": url,
                "created_at": r.get("created_at", 0),
                "prompt": str((r.get("request") or {}).get("prompt", ""))[:140],
            })
    runs.sort(key=lambda r: r["created_at"], reverse=True)
    return {"runs": runs[:50]}


@router.get("/campaigns")
async def list_campaigns(user: dict = Depends(get_current_user)):
    campaigns = ads_db.list_ad_launches(user_id=user["uid"])
    # Ads Manager deep links need the account id; docs from before it was
    # stored get the env account (Phase A: everything launches on it).
    default_account = os.getenv("META_AD_ACCOUNT_ID", "")
    for c in campaigns:
        c.setdefault("account_id", default_account)
    return {"campaigns": campaigns}


@router.get("/campaigns/{launch_id}")
async def get_campaign(launch_id: str, user: dict = Depends(get_current_user)):
    return _own_launch_or_404(launch_id, user["uid"])


@router.post("/copy-suggest")
async def copy_suggest(req: CopySuggestRequest, user: dict = Depends(require_launch_access)):
    video_script = ""
    if req.run_id:
        run = ads_db.get_execution(req.run_id)
        if run and run.get("user_id") == user["uid"]:
            video_script = str((run.get("request") or {}).get("prompt", ""))
    brand = ads_db.get_brand(user["uid"])
    try:
        variants = generate_ad_copy_variants(video_script, req.landing_url, brand,
                                             req.product_hint, req.num_variants)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Copy generation failed: {e}")
    # Variant 0 flattened at the top level = the pre-variant response shape
    # (deployed frontends keep working through the rollout).
    return {"variants": variants, **variants[0]}


@router.post("/launch")
async def launch(req: LaunchRequest, background_tasks: BackgroundTasks,
                 user: dict = Depends(require_launch_access)):
    max_budget = int(os.getenv("ADS_MAX_DAILY_BUDGET_CENTS", "50000"))
    if req.daily_budget_cents > max_budget:
        raise HTTPException(status_code=400,
                            detail=f"Daily budget exceeds cap ({max_budget} minor units)")

    video_url = req.video_url
    if req.run_id:
        run = ads_db.get_execution(req.run_id)
        if not run or run.get("user_id") != user["uid"]:
            raise HTTPException(status_code=404, detail="Run not found")
        video_url = (run.get("result") or {}).get("video_url")
    if not video_url:
        raise HTTPException(status_code=400, detail="Provide run_id or video_url")

    if req.variants:
        copy_variants = [{**v.model_dump(), "ai_generated": req.ai_generated}
                         for v in req.variants]
    elif req.primary_text and req.headline:
        copy_variants = [{"primary_text": req.primary_text, "headline": req.headline,
                          "description": req.description, "ai_generated": req.ai_generated}]
    else:
        raise HTTPException(status_code=400, detail="Provide variants (1-3) or "
                                                    "primary_text + headline "
                                                    "(use /copy-suggest first)")

    account = ads_db.upsert_env_ad_account(
        user["uid"], "meta",
        account_id=os.getenv("META_AD_ACCOUNT_ID", ""),
        page_id=os.getenv("META_PAGE_ID"),
    )
    if not account.get("currency"):
        try:
            info = get_founder_platform().get_account_info()
            account = ads_db.upsert_env_ad_account(
                user["uid"], "meta",
                account_id=os.getenv("META_AD_ACCOUNT_ID", ""),
                page_id=os.getenv("META_PAGE_ID"),
                display_name=info.get("name", ""),
                currency=info.get("currency", ""),
            )
        except Exception as e:
            logger.warning(f"Could not fetch account currency: {e}")

    launch_id = new_launch_id()
    config = {
        "objective": req.objective,
        "daily_budget_cents": req.daily_budget_cents,
        "currency": account.get("currency", ""),
        "landing_url": req.landing_url,
        "cta_type": req.cta_type,
        "targeting": {"countries": req.countries, "age_min": req.age_min, "age_max": req.age_max},
    }
    credits = charge_ad_launch(user["uid"], launch_id,
                               {**config, "num_variants": len(copy_variants)})
    ads_db.create_ad_launch(launch_id, user["uid"], {
        "platform": "meta",
        "ad_account_doc_id": account["doc_id"],
        "account_id": account.get("account_id", ""),
        "source_run_id": req.run_id,
        "video_url": video_url,
        "name": req.name or f"{copy_variants[0]['headline']} — IgniteAds",
        "config": config,
        # `copy` stays = variant 0: metrics_store, card titles, and old
        # deployed frontends read it.
        "copy": copy_variants[0],
        "copy_variants": copy_variants,
        "num_variants": len(copy_variants),
        "credits_charged": credits,
    })

    # Cloud Tasks when configured; BackgroundTasks fallback (run_launch is
    # resume-safe either way)
    from backend.services.cloud_tasks_service import enqueue_launch
    if not enqueue_launch(launch_id, user["uid"]):
        background_tasks.add_task(run_launch, launch_id)

    return {"launch_id": launch_id, "status": "launching"}


@router.post("/task/run")
async def task_run(body: dict, _: None = Depends(require_task_auth)):
    """Cloud Tasks handler — gated by X-Task-Auth (require_task_auth)."""
    import asyncio
    launch_id = body.get("launch_id")
    if not launch_id:
        raise HTTPException(status_code=400, detail="launch_id required")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_launch, launch_id)
    return {"status": "done", "launch_id": launch_id}


@router.post("/task/sync-all")
async def task_sync_all(_: None = Depends(require_task_auth)):
    """Cloud Scheduler entrypoint — refresh every non-terminal launch from
    Meta. Runs synchronously inside the request (Cloud Run throttles CPU
    after the response; tens of launches × ~2 Graph calls fits the 600s
    service timeout comfortably)."""
    import asyncio

    def _run():
        launches = ads_db.list_ad_launches(
            statuses=["launching", "paused", "active", "rejected"])
        synced, errors = 0, []
        for launch in launches:
            if not get_ad_entries(launch.get("platform_ids") or {}):
                continue
            try:
                sync_launch(launch)
                synced += 1
            except Exception as e:
                errors.append({"launch_id": launch["launch_id"], "error": str(e)})
        logger.info("sync-all done", extra={"data": {"synced": synced, "errors": len(errors)}})
        return {"synced": synced, "errors": errors}

    return await asyncio.get_event_loop().run_in_executor(None, _run)


@router.post("/campaigns/{launch_id}/activate")
async def activate(launch_id: str, body: ConfirmBody,
                   user: dict = Depends(require_launch_access)):
    """Start real spend. PAUSED-first contract: requires explicit confirm=true."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to activate (real ad spend)")
    launch = _own_launch_or_404(launch_id, user["uid"])
    if launch["status"] not in ("paused", "active"):
        raise HTTPException(status_code=409, detail=f"Cannot activate from status '{launch['status']}'")
    get_founder_platform().set_status(launch["platform_ids"], "ACTIVE")
    ads_db.update_ad_launch(launch_id, {"status": "active"})
    logger.info("Campaign ACTIVATED via API", extra={"launch_id": launch_id, "user_id": user["uid"]})
    return {"launch_id": launch_id, "status": "active"}


@router.post("/campaigns/{launch_id}/pause")
async def pause(launch_id: str, user: dict = Depends(require_launch_access)):
    launch = _own_launch_or_404(launch_id, user["uid"])
    get_founder_platform().set_status(launch["platform_ids"], "PAUSED")
    ads_db.update_ad_launch(launch_id, {"status": "paused"})
    return {"launch_id": launch_id, "status": "paused"}


@router.post("/campaigns/{launch_id}/sync")
async def sync_status(launch_id: str, user: dict = Depends(require_launch_access)):
    """Refresh Meta review/delivery status + last-7d insights (all variants)."""
    launch = _own_launch_or_404(launch_id, user["uid"])
    return sync_launch(launch)
