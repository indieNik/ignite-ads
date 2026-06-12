"""
Shared sync path — the one code path that refreshes a launch from Meta.

Used by the API route (/campaigns/{id}/sync), the Cloud Scheduler task
(/task/sync-all), and the CLI (scripts/ads/sync_meta_status.py). Pulls
review/delivery status and last-7d insights, stores lifetime + per-variant
aggregates and a capped daily trend history on the launch doc, then mirrors
to the MongoDB analytics store.
"""
from typing import Any, Dict, List, Optional

from backend.logger import get_logger
from backend.services.ads_service.base import get_ad_entries, get_copy_variants
from backend.services.db_service import ads_db

logger = get_logger(__name__)

# Meta effective_status → our launch status (only transitions we act on)
STATUS_MAP = {
    "ACTIVE": "active",
    "PAUSED": "paused",
    "CAMPAIGN_PAUSED": "paused",
    "ADSET_PAUSED": "paused",
    "DISAPPROVED": "rejected",
    "WITH_ISSUES": "rejected",
    "ARCHIVED": "archived",
    "DELETED": "archived",
}

# Trend history kept on the campaign doc (the durable per-ad history lives in
# Mongo metrics_daily; this powers the dashboard sparkline with zero extra reads).
DAILY_HISTORY_DAYS = 30


def sync_launch(launch: Dict[str, Any], platform=None) -> Dict[str, Any]:
    """Refresh one launch from Meta. Returns the fresh launch doc
    (or the unchanged doc when nothing is launched yet)."""
    from backend.services.ads_service.launcher import get_founder_platform

    launch_id = launch["launch_id"]
    ids = launch.get("platform_ids") or {}
    entries = get_ad_entries(ids)
    if not entries:
        return launch
    platform = platform or get_founder_platform()

    meta_status = platform.get_status(ids)
    effective = meta_status.get("effective_status", "UNKNOWN")
    variants = get_copy_variants(launch)

    def headline_for(index: int) -> str:
        return variants[index].get("headline", "") if index < len(variants) else ""

    updates: Dict[str, Any] = {
        "review_status": effective,
        "ads": [{"index": a["index"], "ad_id": a["ad_id"],
                 "effective_status": a["effective_status"],
                 "headline": headline_for(a["index"])}
                for a in meta_status.get("ads") or []],
    }
    mapped = STATUS_MAP.get(effective)
    # Don't overwrite a deliberate local pause/activate with PENDING_REVIEW etc.
    if mapped and mapped != launch["status"]:
        updates["status"] = mapped
    feedback = meta_status.get("ad_review_feedback")
    if feedback:
        updates["error"] = str(feedback)

    insights = platform.get_insights(ids)
    if insights:
        total = lambda k: sum(float(r.get(k, 0) or 0) for r in insights)  # noqa: E731
        updates["lifetime"] = {
            "impressions": int(total("impressions")), "clicks": int(total("clicks")),
            "spend": round(total("spend"), 2),
        }
        updates["variant_metrics"] = variant_metrics(entries, insights, headline_for)
        updates["daily"] = merge_daily(launch.get("daily") or [], insights)

    ads_db.update_ad_launch(launch_id, updates)
    fresh = ads_db.get_ad_launch(launch_id)

    # Mirror into the MongoDB analytics store (agent queries it via MCP)
    from backend.services.metrics_store import metrics_store
    if metrics_store.is_enabled():
        metrics_store.record_daily_metrics(fresh, insights or [])
        metrics_store.record_campaign_summary(fresh)
    return fresh


def variant_metrics(entries: List[Dict], insights: List[Dict], headline_for) -> List[Dict]:
    """Lifetime metrics per variant ad — the A/B winner comparison."""
    index_by_ad = {e["ad_id"]: e["index"] for e in entries}
    by_ad: Dict[Optional[str], Dict[str, Any]] = {}
    for row in insights:
        agg = by_ad.setdefault(row.get("ad_id"), {"impressions": 0, "clicks": 0, "spend": 0.0})
        agg["impressions"] += int(float(row.get("impressions", 0) or 0))
        agg["clicks"] += int(float(row.get("clicks", 0) or 0))
        agg["spend"] += float(row.get("spend", 0) or 0)
    metrics = []
    for ad_id, agg in by_ad.items():
        index = index_by_ad.get(ad_id, 0)
        ctr = round(agg["clicks"] / agg["impressions"] * 100, 2) if agg["impressions"] else 0.0
        metrics.append({"index": index, "ad_id": ad_id, "headline": headline_for(index),
                        "impressions": agg["impressions"], "clicks": agg["clicks"],
                        "spend": round(agg["spend"], 2), "ctr": ctr})
    return sorted(metrics, key=lambda m: m["index"])


def merge_daily(existing: List[Dict], insights: List[Dict]) -> List[Dict]:
    """Fold per-ad insight rows into the doc's daily trend history.
    Upserts by date (the last-7d window overlaps previous syncs), keeps the
    most recent DAILY_HISTORY_DAYS entries."""
    by_date = {d["date"]: dict(d) for d in existing if d.get("date")}
    fresh_dates = {r.get("date_start") for r in insights if r.get("date_start")}
    for date in fresh_dates:
        rows = [r for r in insights if r.get("date_start") == date]
        total = lambda k: sum(float(r.get(k, 0) or 0) for r in rows)  # noqa: E731
        by_date[date] = {
            "date": date,
            "impressions": int(total("impressions")),
            "clicks": int(total("clicks")),
            "spend": round(total("spend"), 2),
        }
    return sorted(by_date.values(), key=lambda d: d["date"])[-DAILY_HISTORY_DAYS:]
