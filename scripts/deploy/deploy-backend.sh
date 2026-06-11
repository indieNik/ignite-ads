#!/bin/bash
# ============================================
# IgniteAds backend → Cloud Run, built REMOTELY via Cloud Build.
# No local Docker — ever (founder's machine cannot run Docker).
# Deploy from main only, after PR merge.
# ============================================
set -e

source "$(dirname "${BASH_SOURCE[0]}")/_load-gcp-config.sh"
_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$_REPO_ROOT/.config/cloud-run-env.yaml"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Missing $ENV_FILE (create from .config/cloud-run-env.yaml.example)"
    exit 1
fi

echo "🚀 Deploying IgniteAds backend (Cloud Build — no local Docker)"
echo "   Project: ${GCP_PROJECT_ID} | Region: ${GCP_REGION} | Service: ${SERVICE_NAME}"
echo ""

cd "$_REPO_ROOT"
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --platform managed \
  --region "${GCP_REGION}" \
  --project "${GCP_PROJECT_ID}" \
  --allow-unauthenticated \
  --timeout 600 \
  --memory 1Gi \
  --cpu 1 \
  --max-instances 5 \
  --min-instances 0 \
  --env-vars-file "$ENV_FILE"

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --region "${GCP_REGION}" --project "${GCP_PROJECT_ID}" --format 'value(status.url)')
echo ""
echo "✅ Deployed: ${SERVICE_URL}"
echo "   Test: curl ${SERVICE_URL}/health"
