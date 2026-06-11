"""
Firebase Admin initialization — shared GCP/Firebase project with IgniteAI.

IgniteAds runs against the SAME Firebase project as the IgniteAI video builder
(shared Auth users, shared Firestore). This service only writes to ad_*
collections; executions/brands/user_credits are read-only (except the credit
cost hook when monetization is enabled).
"""
import firebase_admin
from firebase_admin import credentials, firestore, auth
import os
from dotenv import load_dotenv
from backend.logger import get_logger

logger = get_logger(__name__)

# Load environment variables from repo root
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))
env_path = os.path.join(root_dir, ".env")
load_dotenv(env_path)


def initialize_firebase():
    """Initializes Firebase Admin SDK (idempotent)."""
    try:
        firebase_admin.get_app()
        return
    except ValueError:
        pass

    json_content = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
    options = {"storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET")}

    if json_content:
        import json
        cred = credentials.Certificate(json.loads(json_content))
        firebase_admin.initialize_app(cred, options)
        logger.info("Firebase Admin initialized with FIREBASE_SERVICE_ACCOUNT_JSON")
    elif cred_path:
        if not os.path.isabs(cred_path):
            cred_path = os.path.join(root_dir, cred_path)
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, options)
            logger.info("Firebase Admin initialized with credentials file", extra={"data": {"path": cred_path}})
        else:
            logger.warning("Credential path does not exist, falling back to ADC", extra={"data": {"path": cred_path}})
            firebase_admin.initialize_app(None, options)
    else:
        firebase_admin.initialize_app(None, options)
        logger.info("Firebase Admin initialized (Application Default Credentials)")


def get_firestore_client():
    initialize_firebase()
    return firestore.client()


def verify_token(token: str):
    """Verify a Firebase ID token (must be from the shared project)."""
    try:
        return auth.verify_id_token(token, check_revoked=True)
    except Exception as e:
        raise ValueError(f"Token verification failed: {str(e)}")
