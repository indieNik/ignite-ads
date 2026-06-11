#!/bin/bash
# Loads .config/gcp.env — the single source of truth for GCP deployment target.
# Sourced by deploy and setup scripts. Do not run directly.

# Resolve repo root regardless of caller's cwd.
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_REPO_ROOT="$(cd "$_SCRIPT_DIR/../.." && pwd)"
_CONFIG_FILE="$_REPO_ROOT/.config/gcp.env"

if [ ! -f "$_CONFIG_FILE" ]; then
    echo "❌ Missing $_CONFIG_FILE"
    echo "   This file holds the GCP project + account to deploy to."
    echo "   Create it from .config/gcp.env.example"
    exit 1
fi

# shellcheck disable=SC1090
source "$_CONFIG_FILE"

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID not set in $_CONFIG_FILE}"
: "${GCP_ACCOUNT:?GCP_ACCOUNT not set in $_CONFIG_FILE}"
: "${GCP_REGION:?GCP_REGION not set in $_CONFIG_FILE}"
: "${SERVICE_NAME:?SERVICE_NAME not set in $_CONFIG_FILE}"

# Ensure the configured account is active.
ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null)
if [ -z "$ACTIVE_ACCOUNT" ]; then
    echo "⚠️  No active gcloud account. Run: gcloud auth login $GCP_ACCOUNT"
    exit 1
fi
if [ "$ACTIVE_ACCOUNT" != "$GCP_ACCOUNT" ]; then
    echo "🔄 Switching gcloud account: $ACTIVE_ACCOUNT → $GCP_ACCOUNT"
    gcloud config set account "$GCP_ACCOUNT" 2>/dev/null || {
        echo "❌ $GCP_ACCOUNT is not authenticated. Run: gcloud auth login $GCP_ACCOUNT"
        exit 1
    }
fi
