"""
AdsFactory — routes platform names to AdsPlatform implementations.
Mirrors IgniteAI's MediaFactory pattern. Google Ads slots in here later.
"""
from typing import Optional

from backend.services.ads_service.base import AdsPlatform
from backend.services.ads_service.meta_platform import MetaAdsPlatform


class AdsFactory:
    @staticmethod
    def get_platform(name: str, access_token: str, account_id: str,
                     page_id: Optional[str] = None) -> AdsPlatform:
        name = (name or "").lower()
        if name == "meta":
            return MetaAdsPlatform(access_token, account_id, page_id)
        # elif name == "google":  # Phase: Google Ads
        #     return GoogleAdsPlatform(...)
        raise ValueError(f"Unknown ads platform: {name}")
