"""
Shared launch runner — the one code path that executes a launch state machine
for an existing ad_campaigns doc. Used by the API (BackgroundTasks/Cloud Tasks)
and by the Phase A CLI.
"""
import os
import time
from typing import Any, Dict

from backend.logger import get_logger
from backend.services.ads_service.base import (AdCopy, LaunchConfig, LaunchSpec,
                                                get_copy_variants)
from backend.services.ads_service.factory import AdsFactory
from backend.services.db_service import ads_db

logger = get_logger(__name__)


def get_founder_platform():
    """Platform client from env credentials (Phase A: single founder account)."""
    return AdsFactory.get_platform(
        "meta",
        access_token=os.getenv("META_ACCESS_TOKEN", ""),
        account_id=os.getenv("META_AD_ACCOUNT_ID", ""),
        page_id=os.getenv("META_PAGE_ID"),
    )


def run_launch(launch_id: str) -> Dict[str, Any]:
    """Execute (or resume) a launch. Returns the final launch doc.
    Safe to retry: completed steps are skipped via persisted platform_ids."""
    launch = ads_db.get_ad_launch(launch_id)
    if not launch:
        raise ValueError(f"No launch {launch_id}")

    spec = LaunchSpec(
        launch_id=launch_id,
        name=launch["name"],
        video_url=launch["video_url"],
        thumbnail_url=launch.get("thumbnail_url"),
        page_id=os.getenv("META_PAGE_ID"),
        ad_copies=[AdCopy(**v) for v in get_copy_variants(launch)],
        config=LaunchConfig(**launch["config"]),
    )

    platform = get_founder_platform()
    ads_db.update_ad_launch(launch_id, {"status": "launching", "error": None})
    try:
        ids = platform.launch(
            spec,
            platform_ids=launch.get("platform_ids", {}),
            persist=lambda key, value: ads_db.set_platform_id(launch_id, key, value),
        )
        # Legacy aliases = variant 0, so readers deployed before A/B variants
        # (old frontend, scripts) keep working on new docs.
        for legacy, indexed in (("creative_id", "creative_id_0"), ("ad_id", "ad_id_0")):
            if ids.get(indexed) and not ids.get(legacy):
                ads_db.set_platform_id(launch_id, legacy, ids[indexed])
        ads_db.update_ad_launch(launch_id, {"status": "paused", "launched_at": time.time()})
        logger.info("Launch complete (PAUSED)", extra={"launch_id": launch_id})
    except Exception as e:
        ads_db.update_ad_launch(launch_id, {"status": "error", "error": str(e)})
        logger.error("Launch failed", extra={"launch_id": launch_id, "error": str(e)})
    return ads_db.get_ad_launch(launch_id)
