#!/bin/bash
# Deploy the Angular dashboard to Firebase Hosting (site: igniteai-ads).
# NOTE: Firebase project ignite-ai-01 is owned by a different Google account
# than the Cloud Run project — set FIREBASE_DEPLOY_ACCOUNT in .config/gcp.env.
set -e

_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
[ -f "$_REPO_ROOT/.config/gcp.env" ] && source "$_REPO_ROOT/.config/gcp.env"
: "${FIREBASE_DEPLOY_ACCOUNT:?Set FIREBASE_DEPLOY_ACCOUNT in .config/gcp.env (the Google account that owns the Firebase project)}"

echo "🏗  Building Angular app…"
cd "$_REPO_ROOT/frontend"
npx ng build

echo "🚀 Deploying to Firebase Hosting (site: igniteai-ads, account: $FIREBASE_DEPLOY_ACCOUNT)…"
cd "$_REPO_ROOT"
firebase deploy --only hosting:ads --project ignite-ai-01 --account "$FIREBASE_DEPLOY_ACCOUNT"

echo ""
echo "✅ Live: https://igniteai-ads.web.app (custom domain: https://ads.igniteai.in once DNS is connected)"
