# Unit Costs (COGS) — what each IgniteAds activity costs us

> Written 2026-06-12 as the input to the pricing decision. Prices drift —
> re-verify the linked rate cards before committing to a price. The cost
> hook (`backend/services/ads_service/cost.py`) intentionally still charges
> 0 credits; nothing here changes billing.

## TL;DR

| Activity | Marginal cost | Dominated by |
|---|---|---|
| One launch (1–3 variants) | **≈ $0.003–0.012, effectively $0 under free tiers** | Cloud Run minutes |
| One metrics sync (per campaign) | **< $0.001** | nothing — rounding error |
| Fixed infrastructure / month | **≈ $0 today** | everything is on free tiers |

The real money in this product is the **ad spend itself**, which flows through
the founder's (later: the customer's) Meta invoice — never through us. Our
serving costs are negligible until well past 1,000 launches/month, which means
pricing can be set entirely by **value** (what a launch/test is worth to a
founder), not by cost recovery.

## Per launch

One launch = 1 Gemini copy call + 1 video upload + N creatives + N ads +
~10–16 Firestore writes + 1–6 min of Cloud Run request time.

| Component | Estimate | Basis (verify at) |
|---|---|---|
| Gemini copy call (1–3 variants, one call) | $0.001–0.002 | gemini-2.5-flash ≈ $0.30/1M input + $2.50/1M output tokens; ~1–2k in, 150–450 out — [ai.google.dev/pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| Cloud Run request time (1 vCPU / 1 GiB, 1–6 min — mostly waiting on Meta video processing) | $0.002–0.010 gross; $0 within free tier (180k vCPU-s/mo) | [cloud.google.com/run/pricing](https://cloud.google.com/run/pricing) |
| Firestore writes (doc create + ~1 per launch step; +2 per extra variant) | ~$0.00002, free under 20k writes/day | [firebase.google.com/pricing](https://firebase.google.com/pricing) |
| Meta Graph API (video upload, creatives, campaign, adset, ads) | $0 — the Marketing API is free | — |
| **Total** | **≈ $0.003–0.012; effectively $0 at current volume** | |

Notes:
- A 3-variant launch costs the *same* Gemini call and only +4 Graph POSTs and
  +4 Firestore writes vs a 1-variant launch — A/B testing is essentially free
  for us. Don't price variants by our cost; price them by test value.
- Cloud Run time is dominated by `wait_for_video` polling; if launch volume
  ever matters, moving the wait to Cloud Tasks retries would cut it ~5×.

## Per metrics sync (per campaign)

One sync = 1 Graph GET per ad (status, ≤3) + 1 adset-level insights GET +
~3 Firestore writes + 2 Mongo upserts + a few seconds of Cloud Run.

- All components are free-tier or fractions of a cent → **< $0.001**.
- Scheduled cadence (every 6h × 10 campaigns × 30 days = 1,200 syncs/month)
  stays comfortably inside every free tier.

## Fixed / month

| Item | Cost today | Notes |
|---|---|---|
| Cloud Run `ignite-ads-backend` | $0 idle | `--min-instances 0` (scripts/deploy/deploy-backend.sh) |
| Cloud Scheduler | $0 | `ignite-ads-metrics-sync` is 1 of 3 free jobs |
| Firebase Hosting (landing + app) | $0 | small static assets, free tier |
| Firestore (shared `ignite-ai-01`) | $0 | volumes far below free tier |
| MongoDB Atlas | $0 | M0 free cluster (Cluster0) |
| Meta Marketing API (dev tier) | $0 | Standard Access (App Review) is also free |
| **Total fixed** | **≈ $0/month** | |

First real cost lines to appear with growth, in order:
1. **Gemini** once volume × tokens exceeds the free grant (still ~$2/1k launches).
2. **Cloud Run** past ~50k launch-minutes/month.
3. **Atlas M0 → M10** (~$57/mo) only if analytics volume outgrows 512 MB.

## Implication for pricing (decision still open)

Marginal cost per launch is ~zero, so both candidate models work financially
from day one:

- **Usage-based** (N credits per launch via the existing `charge_ad_launch`
  hook + shared `user_credits` wallet): maps price to the value moment, zero
  COGS risk, trivially implementable.
- **Flat tier** (monthly fee, launch quota): predictable revenue, needs
  subscription state we haven't built.

What we explicitly avoid: **% of ad spend** — early adopters read it as a tax,
and our costs don't scale with spend anyway.
