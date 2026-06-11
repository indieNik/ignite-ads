#!/usr/bin/env python3
"""
Refresh Meta review/delivery status for launches (Phase C precursor).

    python scripts/ads/sync_meta_status.py                # all non-terminal launches
    python scripts/ads/sync_meta_status.py --launch-id adl_xxx
    python scripts/ads/sync_meta_status.py --insights     # also print last-7d metrics
"""
import argparse
import os
import sys

from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from backend.services.ads_service import AdsFactory  # noqa: E402
from backend.services.db_service import ads_db  # noqa: E402

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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--launch-id")
    parser.add_argument("--insights", action="store_true", help="Also fetch last-7d insights")
    args = parser.parse_args()

    platform = AdsFactory.get_platform(
        "meta",
        access_token=os.getenv("META_ACCESS_TOKEN", ""),
        account_id=os.getenv("META_AD_ACCOUNT_ID", ""),
        page_id=os.getenv("META_PAGE_ID"),
    )

    if args.launch_id:
        launch = ads_db.get_ad_launch(args.launch_id)
        launches = [launch] if launch else []
    else:
        launches = ads_db.list_ad_launches(statuses=["launching", "paused", "active", "rejected"])

    if not launches:
        print("No launches to sync.")
        return

    for launch in launches:
        lid = launch["launch_id"]
        ids = launch.get("platform_ids") or {}
        if not ids.get("ad_id"):
            print(f"{lid}: not fully launched (status={launch['status']}), skipping")
            continue

        meta_status = platform.get_status(ids)
        effective = meta_status.get("effective_status", "UNKNOWN")
        review_feedback = meta_status.get("ad_review_feedback")

        updates = {"review_status": effective}
        mapped = STATUS_MAP.get(effective)
        # Don't overwrite a deliberate local pause/activate with PENDING_REVIEW etc.
        if mapped and mapped != launch["status"]:
            updates["status"] = mapped
        if review_feedback:
            updates["error"] = str(review_feedback)
        ads_db.update_ad_launch(lid, updates)

        line = f"{lid}: {launch['status']} → effective_status={effective}"
        if review_feedback:
            line += f"  ⚠️ feedback: {review_feedback}"
        print(line)

        if args.insights:
            insights = platform.get_insights(ids)
            for row in insights:
                print(f"    {row.get('date_start')}: {row.get('impressions', 0)} impr, "
                      f"{row.get('clicks', 0)} clicks, ctr={row.get('ctr', '0')}, "
                      f"spend={row.get('spend', '0')}")
            # Mirror into MongoDB analytics store (agent queries via MCP)
            from backend.services.metrics_store import metrics_store
            if metrics_store.is_enabled():
                fresh = ads_db.get_ad_launch(lid)
                n = metrics_store.record_daily_metrics(fresh, insights)
                metrics_store.record_campaign_summary(fresh)
                print(f"    → {n} daily rows mirrored to MongoDB Atlas")


if __name__ == "__main__":
    main()
