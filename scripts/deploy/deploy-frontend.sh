#!/bin/bash
# Deploy the public site to Firebase Hosting (site: igniteai-ads):
#   /        → landing page (landing/)
#   /app/**  → Angular dashboard (frontend/, built with base-href /app/)
# NOTE: Firebase project ignite-ai-01 is owned by a different Google account
# than the Cloud Run project — set FIREBASE_DEPLOY_ACCOUNT in .config/gcp.env.
set -e

_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
[ -f "$_REPO_ROOT/.config/gcp.env" ] && source "$_REPO_ROOT/.config/gcp.env"
: "${FIREBASE_DEPLOY_ACCOUNT:?Set FIREBASE_DEPLOY_ACCOUNT in .config/gcp.env (the Google account that owns the Firebase project)}"

echo "🏗  Building Angular app (base-href /app/)…"
cd "$_REPO_ROOT/frontend"
npx ng build --base-href /app/

echo "📦 Assembling site (landing at /, app at /app)…"
cd "$_REPO_ROOT"
rm -rf dist-site
mkdir -p dist-site/app
cp -r landing/* dist-site/
cp -r frontend/dist/frontend/browser/* dist-site/app/

echo "🚀 Deploying to Firebase Hosting (site: igniteai-ads, account: $FIREBASE_DEPLOY_ACCOUNT)…"
firebase deploy --only hosting:ads --project ignite-ai-01 --account "$FIREBASE_DEPLOY_ACCOUNT"

echo ""
echo "✅ Live: https://ads.igniteai.in (landing) + https://ads.igniteai.in/app (dashboard)"
