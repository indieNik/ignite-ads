#!/bin/bash
# ============================================
# Cloud Scheduler job: periodic metrics sync.
# POSTs /api/ads/task/sync-all every 6 hours with the X-Task-Auth secret.
# Idempotent — updates the job if it already exists.
#
# Prerequisites:
#   1. ADS_TASK_AUTH_TOKEN set in .config/cloud-run-env.yaml
#   2. Backend deployed with that env (scripts/deploy/deploy-backend.sh)
# ============================================
set -e

source "$(dirname "${BASH_SOURCE[0]}")/_load-gcp-config.sh"
_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$_REPO_ROOT/.config/cloud-run-env.yaml"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Missing $ENV_FILE (create from .config/cloud-run-env.yaml.example)"
    exit 1
fi

TASK_TOKEN=$(grep -E '^ADS_TASK_AUTH_TOKEN:' "$ENV_FILE" | sed -E 's/^[^:]+:[[:space:]]*"?([^"]*)"?[[:space:]]*$/\1/')
if [ -z "$TASK_TOKEN" ]; then
    echo "❌ ADS_TASK_AUTH_TOKEN is empty in $ENV_FILE."
    echo "   Generate one:  python3 -c 'import secrets; print(secrets.token_urlsafe(32))'"
    echo "   Add it to the yaml, redeploy the backend, then re-run this script."
    exit 1
fi

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region "${GCP_REGION}" --project "${GCP_PROJECT_ID}" \
    --format 'value(status.url)')
if [ -z "$SERVICE_URL" ]; then
    echo "❌ Could not resolve Cloud Run URL for ${SERVICE_NAME} — deploy the backend first"
    exit 1
fi

JOB_NAME="ignite-ads-metrics-sync"
JOB_ARGS=(
    --project="${GCP_PROJECT_ID}"
    --location="${GCP_REGION}"
    --schedule="0 */6 * * *"
    --time-zone="Asia/Kolkata"
    --uri="${SERVICE_URL}/api/ads/task/sync-all"
    --http-method=POST
    --headers="X-Task-Auth=${TASK_TOKEN},Content-Type=application/json"
    --message-body='{}'
    --attempt-deadline=540s
)

echo "🕒 Configuring Cloud Scheduler job ${JOB_NAME} → ${SERVICE_URL}/api/ads/task/sync-all (every 6h IST)"
if gcloud scheduler jobs describe "$JOB_NAME" \
    --project="${GCP_PROJECT_ID}" --location="${GCP_REGION}" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "$JOB_NAME" "${JOB_ARGS[@]}"
    echo "✅ Updated existing job."
else
    gcloud scheduler jobs create http "$JOB_NAME" "${JOB_ARGS[@]}"
    echo "✅ Created job."
fi

echo "   Force a run now:  gcloud scheduler jobs run $JOB_NAME --project=${GCP_PROJECT_ID} --location=${GCP_REGION}"
