"""
Cloud Tasks service — durable async ad-launch execution (Phase B).

Ported from IgniteAI. Phase A uses CLI scripts directly; this becomes the
production path when /api/ads/launch ships.

Configuration (set in .config/cloud-run-env.yaml):
  CLOUD_TASKS_QUEUE   — full queue resource path, e.g.
                        projects/PROJECT/locations/REGION/queues/ignite-ads-jobs
  CLOUD_RUN_URL       — base URL of this service
  CLOUD_TASKS_SA_EMAIL — (optional) service account for OIDC token auth

One-time GCP setup:
  gcloud tasks queues create ignite-ads-jobs \\
    --project=$GCP_PROJECT_ID \\
    --location=$GCP_REGION \\
    --max-attempts=3 \\
    --min-backoff=30s \\
    --max-backoff=300s

Graceful degradation: if unconfigured, enqueue_launch() returns False and the
caller falls back to FastAPI BackgroundTasks (local dev workflow).
"""
import os
import json
from typing import Dict, Any

from backend.logger import get_logger

logger = get_logger(__name__)

CLOUD_TASKS_QUEUE = os.getenv("CLOUD_TASKS_QUEUE")
CLOUD_RUN_URL = os.getenv("CLOUD_RUN_URL")
CLOUD_TASKS_SA_EMAIL = os.getenv("CLOUD_TASKS_SA_EMAIL")

# Cloud Tasks hard cap is 30 minutes (1800s). Launches finish in 1–6 min.
TASK_DEADLINE_SECONDS = 600


def enqueue_launch(launch_id: str, user_id: str) -> bool:
    """
    Enqueue an ad-launch task via Cloud Tasks → POST /api/ads/task/run.

    Returns True if enqueued, False if Cloud Tasks is not configured or the
    enqueue fails (caller falls back to BackgroundTasks). The handler re-reads
    the ad_campaigns/{launch_id} doc and resumes idempotently, so retries are
    safe.
    """
    if not CLOUD_TASKS_QUEUE or not CLOUD_RUN_URL:
        return False

    try:
        from google.cloud import tasks_v2
        from google.protobuf import duration_pb2

        client = tasks_v2.CloudTasksClient()
        payload = json.dumps({"launch_id": launch_id, "user_id": user_id}).encode()

        headers = {"Content-Type": "application/json"}
        # /task/run is gated by require_task_auth — present the shared token
        task_token = os.getenv("ADS_TASK_AUTH_TOKEN")
        if task_token:
            headers["X-Task-Auth"] = task_token

        task: Dict[str, Any] = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{CLOUD_RUN_URL.rstrip('/')}/api/ads/task/run",
                "headers": headers,
                "body": payload,
            },
            "dispatch_deadline": duration_pb2.Duration(seconds=TASK_DEADLINE_SECONDS),
        }

        if CLOUD_TASKS_SA_EMAIL:
            task["http_request"]["oidc_token"] = {
                "service_account_email": CLOUD_TASKS_SA_EMAIL,
                "audience": CLOUD_RUN_URL,
            }

        response = client.create_task(parent=CLOUD_TASKS_QUEUE, task=task)
        logger.info("Cloud Task enqueued", extra={"launch_id": launch_id, "data": {"task": response.name}})
        return True

    except Exception as e:
        logger.warning(f"Cloud Tasks enqueue failed (falling back to BackgroundTasks): {e}")
        return False


def is_configured() -> bool:
    """Return True if Cloud Tasks is fully configured for this environment."""
    return bool(CLOUD_TASKS_QUEUE and CLOUD_RUN_URL)
