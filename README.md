# IgniteAds

Launch AI-generated UGC video ads as real ads — Meta (Facebook/Instagram) first, Google Ads later. Companion product to [IgniteAI](https://igniteai.in) (the video builder); shares its Firebase/GCP project but ships as its own service.

**Generate → Launch → Measure → Iterate.**

## Status

Phase A (founder-operated CLI launches) — scaffold complete, Meta verification pending. See [STATUS.md](STATUS.md) for the live tracker and [docs/PLAN.md](docs/PLAN.md) for the full phased plan.

## Quick start (Phase A)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill Meta + Firebase values (see comments inside)

# 1. Token: paste short-lived token from Meta dev console, get a 60-day one
python scripts/ads/exchange_token.py --token <SHORT_TOKEN>

# 2. Dry checks
python scripts/ads/launch_meta_ad.py --check

# 3. Launch a PAUSED campaign from an IgniteAI run
python scripts/ads/launch_meta_ad.py --run-id run_xxx \
    --daily-budget-cents 100 --landing-url https://example.com --ai-copy

# 4. Review in Ads Manager, then activate explicitly (typed confirm)
python scripts/ads/launch_meta_ad.py --activate --launch-id adl_xxx

# Monitor
python scripts/ads/sync_meta_status.py --insights
```

Safety: everything launches **PAUSED**; activation is always a separate, confirmed step; daily budgets are hard-capped via `ADS_MAX_DAILY_BUDGET_CENTS`.

## Deploy

```bash
bash scripts/deploy/deploy-backend.sh    # Cloud Build remote build — no local Docker
```

Requires `.config/gcp.env` and `.config/cloud-run-env.yaml` (create from the `.example` templates).
