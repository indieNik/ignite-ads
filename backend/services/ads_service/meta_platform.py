"""
Meta (Facebook/Instagram) Marketing API implementation of AdsPlatform.

Raw Graph API over `requests` — deliberately NOT the facebook_business SDK
(heavyweight, hard-pins versions). Graph version pinned via
META_GRAPH_API_VERSION env; bump it in one place.

Launch state machine (each step persists its id before the next starts, so a
killed/retried launch resumes without duplicates):
  video → (wait for processing) → creative → campaign → adset → ad

Everything is created with status PAUSED. Activation is a separate explicit
set_status() call — never part of launch().
"""
import os
import time
from typing import Any, Dict, List, Optional

import requests

from backend.logger import get_logger
from backend.services.ads_service.base import AdsPlatform, LaunchSpec, PersistFn

logger = get_logger(__name__)

GRAPH_VERSION = os.getenv("META_GRAPH_API_VERSION", "v23.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

# Steps in launch order with the platform_ids key each one fills.
LAUNCH_STEPS = ["video_id", "creative_id", "campaign_id", "adset_id", "ad_id"]


class MetaAPIError(Exception):
    """Graph API error with Meta's code + human-readable message preserved."""

    def __init__(self, code: Optional[int], message: str, user_msg: str = ""):
        self.code = code
        self.user_msg = user_msg
        super().__init__(f"Meta API error {code}: {message}" + (f" — {user_msg}" if user_msg else ""))


class MetaAdsPlatform(AdsPlatform):
    def __init__(self, access_token: str, account_id: str, page_id: Optional[str] = None):
        if not account_id.startswith("act_"):
            account_id = f"act_{account_id}"
        self.access_token = access_token
        self.account_id = account_id
        self.page_id = page_id

    # ----- HTTP helpers -------------------------------------------------

    def _request(self, method: str, path: str, params: Optional[Dict] = None,
                 data: Optional[Dict] = None) -> Dict[str, Any]:
        params = dict(params or {})
        params["access_token"] = self.access_token
        url = f"{GRAPH_BASE}/{path.lstrip('/')}"
        resp = requests.request(method, url, params=params, json=data, timeout=120)
        try:
            body = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise MetaAPIError(None, f"Non-JSON response: {resp.text[:200]}")
        if "error" in body:
            err = body["error"]
            raise MetaAPIError(err.get("code"), err.get("message", "unknown"),
                               err.get("error_user_msg", ""))
        return body

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        return self._request("GET", path, params=params)

    def _post(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", path, data=data)

    # ----- Dry checks (verification step 0) -----------------------------

    def whoami(self) -> Dict[str, Any]:
        """Token sanity: returns the token's user + accessible ad accounts."""
        me = self._get("me", params={"fields": "id,name"})
        accounts = self._get("me/adaccounts", params={"fields": "id,name,currency,account_status"})
        return {"user": me, "ad_accounts": accounts.get("data", [])}

    def check_page(self) -> Dict[str, Any]:
        if not self.page_id:
            raise ValueError("page_id not set")
        return self._get(self.page_id, params={"fields": "id,name"})

    def get_account_info(self) -> Dict[str, Any]:
        return self._get(self.account_id, params={"fields": "id,name,currency,account_status"})

    # ----- Launch steps -------------------------------------------------

    def upload_video(self, video_url: str, name: str) -> str:
        body = self._post(f"{self.account_id}/advideos",
                          {"file_url": video_url, "name": name})
        return body["id"]

    def wait_for_video(self, video_id: str, timeout_seconds: int = 300) -> None:
        deadline = time.time() + timeout_seconds
        delay = 5
        while time.time() < deadline:
            body = self._get(video_id, params={"fields": "status"})
            status = (body.get("status") or {}).get("video_status")
            if status == "ready":
                return
            if status == "error":
                raise MetaAPIError(None, f"Video {video_id} failed processing", str(body.get("status")))
            time.sleep(delay)
            delay = min(delay * 1.5, 30)
        raise TimeoutError(f"Video {video_id} not ready after {timeout_seconds}s")

    def get_video_thumbnail(self, video_id: str) -> Optional[str]:
        try:
            body = self._get(f"{video_id}/thumbnails")
            thumbs = body.get("data", [])
            if not thumbs:
                return None
            preferred = next((t for t in thumbs if t.get("is_preferred")), thumbs[0])
            return preferred.get("uri")
        except MetaAPIError as e:
            logger.warning(f"Thumbnail fetch failed for video {video_id}: {e}")
            return None

    def create_creative(self, spec: LaunchSpec, video_id: str) -> str:
        thumbnail = self.get_video_thumbnail(video_id) or spec.thumbnail_url
        if not thumbnail:
            raise MetaAPIError(None, "No thumbnail available: Meta requires image_url "
                                     "for video creatives. Pass thumbnail_url in the spec.")
        video_data: Dict[str, Any] = {
            "video_id": video_id,
            "image_url": thumbnail,
            "message": spec.ad_copy.primary_text,
            "title": spec.ad_copy.headline,
            "link_description": spec.ad_copy.description,
            "call_to_action": {
                "type": spec.config.cta_type,
                "value": {"link": spec.config.landing_url},
            },
        }
        body = self._post(f"{self.account_id}/adcreatives", {
            "name": f"{spec.name} — creative",
            "object_story_spec": {"page_id": spec.page_id or self.page_id,
                                  "video_data": video_data},
        })
        return body["id"]

    def create_campaign(self, spec: LaunchSpec) -> str:
        body = self._post(f"{self.account_id}/campaigns", {
            "name": spec.name,
            "objective": spec.config.objective,
            "status": "PAUSED",
            "special_ad_categories": [],
        })
        return body["id"]

    def create_adset(self, spec: LaunchSpec, campaign_id: str) -> str:
        t = spec.config.targeting
        targeting: Dict[str, Any] = {
            "geo_locations": {"countries": t.countries},
            "age_min": t.age_min,
            "age_max": t.age_max,
            # Explicit opt-out keeps targeting deterministic; required field on
            # newer Graph versions. Flip to 1 to let Advantage+ expand audience.
            "targeting_automation": {"advantage_audience": 0},
        }
        if t.genders:
            targeting["genders"] = t.genders

        payload: Dict[str, Any] = {
            "name": f"{spec.name} — adset",
            "campaign_id": campaign_id,
            "daily_budget": spec.config.daily_budget_cents,
            "billing_event": "IMPRESSIONS",
            "optimization_goal": "LINK_CLICKS",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "targeting": targeting,
            "status": "PAUSED",
        }
        if spec.config.start_time:
            payload["start_time"] = spec.config.start_time
        if spec.config.end_time:
            payload["end_time"] = spec.config.end_time
        body = self._post(f"{self.account_id}/adsets", payload)
        return body["id"]

    def create_ad(self, spec: LaunchSpec, adset_id: str, creative_id: str) -> str:
        body = self._post(f"{self.account_id}/ads", {
            "name": f"{spec.name} — ad",
            "adset_id": adset_id,
            "creative": {"creative_id": creative_id},
            "status": "PAUSED",
        })
        return body["id"]

    # ----- The state machine --------------------------------------------

    def launch(self, spec: LaunchSpec, platform_ids: Dict[str, str],
               persist: PersistFn) -> Dict[str, str]:
        ids = dict(platform_ids or {})

        def step(key: str, fn) -> str:
            if ids.get(key):
                logger.info(f"Skipping {key} (already done)", extra={"launch_id": spec.launch_id, "step": key})
                return ids[key]
            value = fn()
            ids[key] = value
            persist(key, value)
            logger.info(f"Step complete: {key}={value}", extra={"launch_id": spec.launch_id, "step": key})
            return value

        video_id = step("video_id", lambda: self.upload_video(spec.video_url, spec.name))
        # wait_for_video is safe to repeat — a ready video returns immediately
        self.wait_for_video(video_id)
        creative_id = step("creative_id", lambda: self.create_creative(spec, video_id))
        campaign_id = step("campaign_id", lambda: self.create_campaign(spec))
        adset_id = step("adset_id", lambda: self.create_adset(spec, campaign_id))
        step("ad_id", lambda: self.create_ad(spec, adset_id, creative_id))
        return ids

    # ----- Post-launch management ----------------------------------------

    def get_status(self, platform_ids: Dict[str, str]) -> Dict[str, Any]:
        ad_id = platform_ids.get("ad_id")
        if not ad_id:
            return {"effective_status": "NOT_LAUNCHED"}
        body = self._get(ad_id, params={"fields": "effective_status,configured_status,ad_review_feedback"})
        return body

    def set_status(self, platform_ids: Dict[str, str], status: str) -> None:
        if status not in ("ACTIVE", "PAUSED"):
            raise ValueError(f"Invalid status {status}")
        # Activating requires all three levels ACTIVE (everything is created
        # PAUSED); pausing the campaign alone stops delivery, but we keep the
        # three levels consistent either way.
        for key in ("campaign_id", "adset_id", "ad_id"):
            obj_id = platform_ids.get(key)
            if obj_id:
                self._post(obj_id, {"status": status})

    def get_insights(self, platform_ids: Dict[str, str],
                     date_preset: str = "last_7d") -> List[Dict[str, Any]]:
        ad_id = platform_ids.get("ad_id")
        if not ad_id:
            return []
        body = self._get(f"{ad_id}/insights", params={
            "fields": "impressions,clicks,ctr,spend,actions",
            "date_preset": date_preset,
            "time_increment": 1,
        })
        return body.get("data", [])
