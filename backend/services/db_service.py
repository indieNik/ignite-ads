"""
Firestore persistence for IgniteAds — shared project with IgniteAI.

Writes ONLY to ad_* collections (+ refunds when monetized). Reads IgniteAI's
executions (video URLs/scripts) and brands (brand kit) read-only.

Collections:
  ad_accounts/{user_id}_{platform}   — connection records, token descriptors
  ad_campaigns/{launch_id}           — launch state machine docs
  ad_campaigns/{launch_id}/metrics/{YYYY-MM-DD} — Phase C daily snapshots
"""
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from google.cloud import firestore

from backend.firebase_setup import get_firestore_client
from backend.logger import get_logger

logger = get_logger(__name__)

AD_ACCOUNTS = "ad_accounts"
AD_CAMPAIGNS = "ad_campaigns"


def new_launch_id() -> str:
    return f"adl_{uuid.uuid4().hex}"


class AdsDB:
    def __init__(self):
        self._db = None

    @property
    def db(self):
        if self._db is None:
            self._db = get_firestore_client()
        return self._db

    # ----- ad_accounts ----------------------------------------------------

    def account_doc_id(self, user_id: str, platform: str = "meta") -> str:
        return f"{user_id}_{platform}"

    def upsert_env_ad_account(self, user_id: str, platform: str, account_id: str,
                              page_id: Optional[str], display_name: str = "",
                              currency: str = "") -> Dict[str, Any]:
        """Phase A: founder account whose token lives in env (never in Firestore)."""
        doc_id = self.account_doc_id(user_id, platform)
        data = {
            "user_id": user_id,
            "platform": platform,
            "account_id": account_id,
            "page_id": page_id,
            "token": {"type": "env", "ref": "META_ACCESS_TOKEN"},
            "status": "connected",
            "display_name": display_name,
            "currency": currency,
            "updated_at": time.time(),
        }
        ref = self.db.collection(AD_ACCOUNTS).document(doc_id)
        if not ref.get().exists:
            data["connected_at"] = time.time()
        ref.set(data, merge=True)
        return self.get_ad_account(doc_id)

    def get_ad_account(self, doc_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db.collection(AD_ACCOUNTS).document(doc_id).get()
        return {**doc.to_dict(), "doc_id": doc.id} if doc.exists else None

    @staticmethod
    def resolve_access_token(account: Dict[str, Any]) -> str:
        """Single token-resolution path for both phases."""
        token = account.get("token") or {}
        if token.get("type") == "env":
            value = os.getenv(token.get("ref", "META_ACCESS_TOKEN"), "")
            if not value:
                raise ValueError(f"Env var {token.get('ref')} is empty — set the access token in .env")
            return value
        if token.get("type") == "encrypted":
            # Phase B: Fernet-encrypted customer tokens
            from cryptography.fernet import Fernet
            key = os.getenv("ADS_TOKEN_ENC_KEY")
            if not key:
                raise ValueError("ADS_TOKEN_ENC_KEY not set — cannot decrypt customer token")
            return Fernet(key.encode()).decrypt(token["ciphertext"].encode()).decode()
        raise ValueError(f"Unknown token descriptor type: {token.get('type')}")

    # ----- ad_campaigns (launch docs) --------------------------------------

    def create_ad_launch(self, launch_id: str, user_id: str,
                         data: Dict[str, Any]) -> bool:
        """Transactional create-if-absent keyed on launch_id (the idempotency
        guard against double-launch). Returns False if the doc already exists."""
        ref = self.db.collection(AD_CAMPAIGNS).document(launch_id)

        @firestore.transactional
        def _create(transaction):
            if ref.get(transaction=transaction).exists:
                return False
            transaction.set(ref, {
                **data,
                "launch_id": launch_id,
                "user_id": user_id,
                "platform_ids": {},
                "status": "draft",
                "credits_charged": 0,
                "created_at": time.time(),
                "updated_at": time.time(),
            })
            return True

        return _create(self.db.transaction())

    def update_ad_launch(self, launch_id: str, fields: Dict[str, Any]) -> None:
        fields["updated_at"] = time.time()
        self.db.collection(AD_CAMPAIGNS).document(launch_id).set(fields, merge=True)

    def set_platform_id(self, launch_id: str, key: str, value: str) -> None:
        """Persist one launch-step result — makes interrupted launches resumable."""
        self.db.collection(AD_CAMPAIGNS).document(launch_id).set(
            {"platform_ids": {key: value}, "updated_at": time.time()}, merge=True)

    def get_ad_launch(self, launch_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db.collection(AD_CAMPAIGNS).document(launch_id).get()
        return doc.to_dict() if doc.exists else None

    def list_ad_launches(self, user_id: Optional[str] = None,
                         statuses: Optional[List[str]] = None,
                         limit: int = 100) -> List[Dict[str, Any]]:
        q = self.db.collection(AD_CAMPAIGNS)
        if user_id:
            q = q.where("user_id", "==", user_id)
        if statuses:
            q = q.where("status", "in", statuses)
        q = q.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)
        return [d.to_dict() for d in q.stream()]

    def save_metrics_snapshot(self, launch_id: str, date_key: str,
                              metrics: Dict[str, Any]) -> None:
        """Phase C: daily metrics snapshot under the launch doc."""
        self.db.collection(AD_CAMPAIGNS).document(launch_id) \
            .collection("metrics").document(date_key) \
            .set({**metrics, "synced_at": time.time()}, merge=True)

    # ----- read-only views into IgniteAI collections -----------------------

    def get_execution(self, run_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db.collection("executions").document(run_id).get()
        return doc.to_dict() if doc.exists else None

    def get_execution_video_url(self, run_id: str) -> Optional[str]:
        run = self.get_execution(run_id)
        if not run:
            return None
        return (run.get("result") or {}).get("video_url")

    def get_brand(self, user_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db.collection("brands").document(user_id).get()
        return doc.to_dict() if doc.exists else None


ads_db = AdsDB()
