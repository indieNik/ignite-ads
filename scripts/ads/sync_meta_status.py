#!/usr/bin/env python3
"""
Refresh Meta review/delivery status + metrics for launches.

Thin CLI over backend.services.sync_service.sync_launch — the same code path
the API route and the Cloud Scheduler task use.

    python scripts/ads/sync_meta_status.py                # all non-terminal launches
    python scripts/ads/sync_meta_status.py --launch-id adl_xxx
    python scripts/ads/sync_meta_status.py --insights     # also print per-day metrics
"""
import argparse
import os
import sys

from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from backend.services.ads_service import AdsFactory, get_ad_entries  # noqa: E402
from backend.services.db_service import ads_db  # noqa: E402
from backend.services.sync_service import sync_launch  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--launch-id")
    parser.add_argument("--insights", action="store_true", help="Also print per-day + per-variant metrics")
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
        if not get_ad_entries(launch.get("platform_ids") or {}):
            print(f"{lid}: not fully launched (status={launch['status']}), skipping")
            continue

        fresh = sync_launch(launch, platform=platform)

        line = f"{lid}: {launch['status']} → effective_status={fresh.get('review_status')}"
        per_ad = fresh.get("ads") or []
        if len(per_ad) > 1:
            line += " [" + ", ".join(f"v{a['index'] + 1}={a['effective_status']}" for a in per_ad) + "]"
        print(line)

        if args.insights:
            for day in fresh.get("daily") or []:
                print(f"    {day['date']}: {day['impressions']} impr, "
                      f"{day['clicks']} clicks, spend={day['spend']}")
            for m in fresh.get("variant_metrics") or []:
                print(f"    v{m['index'] + 1} \"{m['headline']}\": {m['impressions']} impr, "
                      f"{m['clicks']} clicks, ctr={m['ctr']}%, spend={m['spend']}")


if __name__ == "__main__":
    main()
