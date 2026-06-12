"""
AdsPlatform abstraction — the contract every ad platform implementation
(Meta today, Google Ads later) must satisfy.

Pattern ported from IgniteAI's engine/media/factory.py (MediaProvider ABC).
"""
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


class AdCopy(BaseModel):
    primary_text: str
    headline: str
    description: str = ""
    ai_generated: bool = False


class Targeting(BaseModel):
    countries: List[str] = ["IN"]
    age_min: int = 18
    age_max: int = 65
    genders: Optional[List[int]] = None  # Meta: 1=male, 2=female; None=all


class LaunchConfig(BaseModel):
    objective: str = "OUTCOME_TRAFFIC"  # or OUTCOME_SALES
    daily_budget_cents: int = Field(gt=0)  # minor units of the ad account currency
    currency: str = "USD"
    landing_url: str
    cta_type: str = "LEARN_MORE"  # Meta CTA enum: LEARN_MORE, SHOP_NOW, SIGN_UP, ...
    targeting: Targeting = Targeting()
    start_time: Optional[str] = None  # ISO 8601; None = start when activated
    end_time: Optional[str] = None


MAX_COPY_VARIANTS = 3


class LaunchSpec(BaseModel):
    """Everything a platform needs to take a video URL to a paused ad."""
    launch_id: str
    name: str  # base name for campaign/adset/ad
    video_url: str  # must be publicly fetchable by the platform
    thumbnail_url: Optional[str] = None  # fallback if platform can't auto-thumbnail
    page_id: Optional[str] = None  # Meta: the FB Page the ad posts as
    # One ad per copy variant, all sharing the video/campaign/adset (A/B test).
    # Named ad_copies (not "copies"): "copy" shadows BaseModel.copy.
    ad_copies: List[AdCopy] = Field(min_length=1, max_length=MAX_COPY_VARIANTS)
    config: LaunchConfig


# ----- Variant-aware readers over both doc shapes ------------------------
# Launch docs created before A/B variants have singular `copy` and singular
# `platform_ids.creative_id`/`ad_id`. There is no data migration: every read
# path goes through these two helpers, which treat the legacy shape as a
# single variant at index 0.

def get_copy_variants(launch: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Copy variants of a launch doc, oldest shape included."""
    variants = launch.get("copy_variants")
    if variants:
        return list(variants)
    return [launch["copy"]] if launch.get("copy") else []


def get_ad_entries(platform_ids: Dict[str, Any]) -> List[Dict[str, Any]]:
    """[{index, ad_id, creative_id}] from indexed or legacy-singular ids."""
    entries = []
    for i in range(MAX_COPY_VARIANTS):
        ad_id = platform_ids.get(f"ad_id_{i}")
        if ad_id:
            entries.append({"index": i, "ad_id": ad_id,
                            "creative_id": platform_ids.get(f"creative_id_{i}")})
    if not entries and platform_ids.get("ad_id"):
        entries.append({"index": 0, "ad_id": platform_ids["ad_id"],
                        "creative_id": platform_ids.get("creative_id")})
    return entries


# persist callback: persist(step_key: str, platform_id: str) — called after each
# successful step so partial progress lands in Firestore (resumable launches).
PersistFn = Callable[[str, str], None]


class AdsPlatform(ABC):
    """Abstract ad platform. All ads are created PAUSED — activation is always
    a separate, explicit call to set_status()."""

    @abstractmethod
    def upload_video(self, video_url: str, name: str) -> str:
        """Upload a video by URL to the ad account. Returns platform video id."""

    @abstractmethod
    def wait_for_video(self, video_id: str, timeout_seconds: int = 300) -> None:
        """Block until the uploaded video finishes processing (or raise)."""

    @abstractmethod
    def launch(
        self,
        spec: LaunchSpec,
        platform_ids: Dict[str, str],
        persist: PersistFn,
    ) -> Dict[str, str]:
        """
        Run the full launch state machine (video → creative → campaign →
        adset → ad), skipping any step whose id already exists in
        platform_ids. Returns the completed platform_ids dict.
        """

    @abstractmethod
    def get_status(self, platform_ids: Dict[str, str]) -> Dict[str, Any]:
        """Fetch effective/review status rolled up across all ads of the
        launch, with per-ad detail under "ads"."""

    @abstractmethod
    def set_status(self, platform_ids: Dict[str, str], status: str) -> None:
        """Set ACTIVE or PAUSED across the campaign/adset and every ad."""

    @abstractmethod
    def get_insights(
        self, platform_ids: Dict[str, str], date_preset: str = "last_7d"
    ) -> List[Dict[str, Any]]:
        """Fetch daily performance metrics (impressions, clicks, ctr, spend,
        actions) for every ad of the launch; rows carry ad_id."""
