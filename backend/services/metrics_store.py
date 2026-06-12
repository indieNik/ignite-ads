"""
MongoDB Atlas analytics store — the agent-queryable performance layer.

Division of labor:
  - Firestore  = operational state (launch state machine, tokens, ownership)
  - MongoDB    = analytics (daily metric snapshots + campaign summaries) that
                 the agent queries via the MongoDB MCP server for winner/loser
                 analysis and creative-iteration proposals
                 (see directives/analyze_ad_performance.md and .mcp.json)

Graceful no-op when MONGODB_URI is unset — Phase A works without Atlas.

Setup: free MongoDB Atlas cluster → put the connection string in .env:
  MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
Database: igniteads · Collections: metrics_daily, campaign_summaries
"""
import os
import time
from typing import Any, Dict, Optional

from backend.logger import get_logger

logger = get_logger(__name__)

DB_NAME = "igniteads"


RETRY_INTERVAL_SECS = 60


class MetricsStore:
    def __init__(self):
        self._client = None
        self._last_attempt = 0.0

    @property
    def db(self):
        # Re-attempt periodically rather than latching off on first failure —
        # transient causes (Atlas IP allowlist updates, cold networking) heal
        # without needing an instance restart.
        if self._client is None and time.time() - self._last_attempt > RETRY_INTERVAL_SECS:
            self._last_attempt = time.time()
            uri = os.getenv("MONGODB_URI")
            if uri:
                try:
                    import certifi
                    from pymongo import MongoClient
                    # tlsCAFile: macOS/minimal-container Pythons often lack
                    # system CA certs — Atlas TLS fails without certifi's bundle
                    client = MongoClient(uri, serverSelectionTimeoutMS=4000,
                                         tlsCAFile=certifi.where())
                    client.admin.command("ping")
                    self._client = client
                    logger.info("MongoDB Atlas analytics store connected")
                except Exception as e:
                    logger.warning(f"MongoDB unavailable, analytics disabled: {e}")
        return self._client[DB_NAME] if self._client is not None else None

    def is_enabled(self) -> bool:
        return self.db is not None

    def record_daily_metrics(self, launch: Dict[str, Any], insights: list) -> int:
        """Upsert one document per (launch, day, ad) from Meta Insights rows.
        Rows are per-ad (one ad per copy variant), so the agent can compare
        variants directly."""
        from backend.services.ads_service.base import get_ad_entries, get_copy_variants

        db = self.db
        if db is None or not insights:
            return 0
        variants = get_copy_variants(launch)
        index_by_ad = {e["ad_id"]: e["index"]
                       for e in get_ad_entries(launch.get("platform_ids") or {})}
        written = 0
        for row in insights:
            date = row.get("date_start")
            if not date:
                continue
            ad_id = row.get("ad_id", "")
            index = index_by_ad.get(ad_id, 0)
            headline = (variants[index].get("headline", "") if index < len(variants)
                        else (launch.get("copy") or {}).get("headline", ""))
            db.metrics_daily.update_one(
                {"launch_id": launch["launch_id"], "date": date, "ad_id": ad_id},
                {"$set": {
                    "launch_id": launch["launch_id"],
                    "user_id": launch.get("user_id"),
                    "platform": launch.get("platform", "meta"),
                    "ad_id": ad_id,
                    "variant_index": index,
                    "headline": headline,
                    "date": date,
                    "impressions": int(float(row.get("impressions", 0) or 0)),
                    "clicks": int(float(row.get("clicks", 0) or 0)),
                    "ctr": float(row.get("ctr", 0) or 0),
                    "spend": float(row.get("spend", 0) or 0),
                    "synced_at": time.time(),
                }},
                upsert=True,
            )
            written += 1
        return written

    def record_campaign_summary(self, launch: Dict[str, Any]) -> None:
        """Upsert the rollup the agent aggregates over for winner/loser calls."""
        db = self.db
        if db is None:
            return
        lifetime = launch.get("lifetime") or {}
        db.campaign_summaries.update_one(
            {"launch_id": launch["launch_id"]},
            {"$set": {
                "launch_id": launch["launch_id"],
                "user_id": launch.get("user_id"),
                "platform": launch.get("platform", "meta"),
                "name": launch.get("name", ""),
                "headline": (launch.get("copy") or {}).get("headline", ""),
                "primary_text": (launch.get("copy") or {}).get("primary_text", ""),
                "status": launch.get("status"),
                "review_status": launch.get("review_status"),
                "daily_budget_cents": (launch.get("config") or {}).get("daily_budget_cents"),
                "currency": (launch.get("config") or {}).get("currency", ""),
                "landing_url": (launch.get("config") or {}).get("landing_url", ""),
                "source_run_id": launch.get("source_run_id"),
                "num_variants": launch.get("num_variants", 1),
                "variant_metrics": launch.get("variant_metrics") or [],
                "impressions": lifetime.get("impressions", 0),
                "clicks": lifetime.get("clicks", 0),
                "spend": lifetime.get("spend", 0),
                "launched_at": launch.get("launched_at"),
                "updated_at": time.time(),
            }},
            upsert=True,
        )


metrics_store = MetricsStore()
