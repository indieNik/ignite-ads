"""
THE cost hook — the single place where ad launches are metered.

Monetization is intentionally undecided. Today every launch costs 0 credits.
When pricing lands, implement inside charge_ad_launch() only:

    cost = _compute_cost(config)            # e.g. flat 5 credits per launch
    if not ads_db.deduct_credits(user_id, cost):   # shared user_credits collection
        raise InsufficientCreditsError(cost)
    return cost

Refunds on failed launches should reuse the IgniteAI idempotent-refund pattern:
a deterministic refunds/{launch_id}_refund doc guarding a transactional
credit increment (see IgniteAI projects/backend/services/db_service/credits.py).
"""
from typing import Any, Dict

from backend.logger import get_logger

logger = get_logger(__name__)


class InsufficientCreditsError(Exception):
    def __init__(self, required: int):
        self.required = required
        super().__init__(f"Insufficient credits: {required} required")


def charge_ad_launch(user_id: str, launch_id: str, config: Dict[str, Any]) -> int:
    """Charge for an ad launch. Returns credits charged (0 while unmonetized)."""
    logger.info("Cost hook: launch is free (monetization undecided)",
                extra={"user_id": user_id, "launch_id": launch_id, "credits": 0})
    return 0
