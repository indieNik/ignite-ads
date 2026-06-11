# IgniteAds: Standalone Ads-Launch Platform (Meta first, Google Ads later)

## Context

IgniteAI generates UGC video ads but stops at the download button. This project closes the loop — actually launching those creatives as real ads — as a **standalone application** in its own repo, treating IgniteAI as one creative source (any public video URL works). Decisions made with the founder:

- **Standalone app, shared infra**: separate codebase + separate Cloud Run service, but the **same Firebase/GCP project** — shared Firebase Auth (same user accounts, ID tokens verify in both backends), shared Firestore (new `ad_*` collections; read-only access to `executions` for video URLs), shared GCS.
- **Stack mirrors IgniteAI**: FastAPI backend + Angular frontend (frontend deferred to Phase B), so patterns/code port nearly verbatim.
- **Workspace**: new sibling dir `~/Projects/AI-Projects/ignite-ads/` with its own GitHub repo (created via `gh repo create`).
- **Phased**: Phase A = founder-operated (own Meta ad account, CLI/directive-driven, no Meta App Review) to validate fast. Phase B = multi-tenant self-serve OAuth. Data model multi-tenant from day one.
- **Meta first**; Google Ads slots in later via an `AdsPlatform` abstraction.
- **Monetization undecided**: single cost hook charging 0 credits for now (shared `user_credits` collection makes credit-metering trivial later).
- **MCP role**: Meta Ads MCP (e.g., pipeboard) optionally added to the founder's Claude config for *read-only inspection*. The launch path is deterministic Python (3-layer principle: directives → agent → scripts) — a shared `MetaAdsClient` used by both the Phase A CLI runner and the Phase B FastAPI routes.

## Architecture decisions

1. **Raw Graph API via `requests`** — not the `facebook_business` SDK. ~7 endpoints. Version pinned via `META_GRAPH_API_VERSION` env (default `v23.0`), base URL in one constant.
2. **`AdsPlatform` ABC + `AdsFactory`** (pattern ported from IgniteAI's `engine/media/factory.py`). Methods: `upload_video`, `wait_for_video`, `launch(spec)`, `get_status`, `set_status`, `get_insights`.
3. **Token storage**: `ad_accounts` docs carry a token descriptor — `{type: "env", ref: "META_ACCESS_TOKEN"}` for the founder (Phase A, token never in Firestore); `{type: "encrypted", ciphertext}` (Fernet, key in `ADS_TOKEN_ENC_KEY`) for Phase B customers. One resolver: `resolve_access_token(doc)`.
4. **Safety rails**: ads always created `PAUSED`; activation is a separate explicit step; hard daily-budget cap (`ADS_MAX_DAILY_BUDGET_CENTS`); idempotent step-resume launch state machine keyed on `launch_id` (no double-launch on Cloud Tasks retry).

## Phase 0 — Scaffold the standalone workspace

Create `~/Projects/AI-Projects/ignite-ads/`:

```
ignite-ads/
├── backend/                      # FastAPI app (Cloud Run service: ignite-ads-backend)
│   ├── main.py                   # app + router registration + CORS
│   ├── dependencies.py           # get_current_user (ported)
│   ├── firebase_setup.py         # Firebase Admin init (ported)
│   ├── logger.py                 # (ported)
│   ├── schemas.py                # pydantic models
│   ├── routers/                  # ads endpoints (Phase B)
│   └── services/
│       ├── ads_service/          # the core (Phase A)
│       ├── db_service.py         # Firestore ops for ad_* collections
│       └── cloud_tasks_service.py  # (ported, own queue: ignite-ads-jobs)
├── frontend/                     # Angular app (Phase B — scaffold only later)
├── scripts/
│   ├── ads/                      # Phase A CLI runners
│   └── deploy/                   # deploy-backend.sh + _load-gcp-config.sh (ported)
├── directives/                   # SOPs (launch_meta_ad.md, ...)
├── .config/                      # gcp.env, cloud-run-env.yaml (gitignored) + .example templates
├── CLAUDE.md (= AGENTS.md = GEMINI.md), README.md, .gitignore, .env.example
├── requirements.txt              # single source of truth (IgniteAI convention)
└── Dockerfile
```

**Port manifest** (copy-adapt from the IgniteAI repo — "get things ready to migrate"):
- `projects/backend/dependencies.py` → `backend/dependencies.py` (get_current_user, Firebase token verify)
- `projects/backend/firebase_setup.py` → `backend/firebase_setup.py`
- `projects/backend/services/cloud_tasks_service.py` → adapted (new queue name, task_type `ad_launch`)
- `projects/backend/services/db_service/credits.py` deduct/refund pattern → referenced by the cost hook (operates on the shared `user_credits` collection)
- `scripts/deploy/_load-gcp-config.sh` + a deploy script → `scripts/deploy/` (same `.config/gcp.env` convention, `SERVICE_NAME=ignite-ads-backend`)
- `Dockerfile`, `.gitignore`, logger — adapted
- CLAUDE.md: same 3-layer agent instructions, trimmed to this repo

**Setup steps**: `git init` → scaffold → `gh repo create ignite-ads --private` → first commit on `main`, then dated feature branches per IgniteAI convention. Same service account credentials (`.env` GOOGLE_APPLICATION_CREDENTIALS / ADC) since it's the same GCP project.

## Firestore schemas (shared project, new collections)

```
ad_accounts/{user_id}_meta
  user_id, platform, account_id ("act_..."), page_id, instagram_actor_id?
  token: {type, ref|ciphertext, expires_at}, status: connected|expired|revoked
  display_name, currency, connected_at, updated_at

ad_campaigns/{launch_id}            # launch_id = adl_{uuid.hex} — idempotency key
  user_id, platform, ad_account_doc_id, source_run_id?, video_url
  config: {objective, daily_budget_cents, currency, start/end_time, landing_url,
           cta_type, targeting {countries, age, genders, interests}, placements}
  copy: {primary_text, headline, description, ai_generated}
  platform_ids: {video_id, creative_id, campaign_id, adset_id, ad_id}   # filled step-by-step → resumable
  status: draft|launching|paused|active|rejected|error|archived
  review_status, error, credits_charged, created_at, updated_at, launched_at
  lifetime: {spend, impressions, clicks, ctr, conversions, last_synced_at}   # Phase C

ad_campaigns/{launch_id}/metrics/{YYYY-MM-DD}   # Phase C daily snapshots
```

`source_run_id` is optional: when set, video URL is read from IgniteAI's `executions/{run_id}.result.video_url`; otherwise any public video URL can be supplied directly (standalone-first).

## Phase A — Founder-operated launches (ship first)

Launch real PAUSED Meta campaigns via CLI + directive. No UI.

**Meta app prerequisite: ALREADY DONE.** Founder has an existing Business-type app ("My Insta Manager", App ID `2140108452878655`, Live mode) with the Marketing API product added and `ads_management` / `ads_read` / `read_insights` grantable from the Marketing API → Tools token generator. Notes:
- Tokens from that tool are short-lived (~1–2h) → add `scripts/ads/exchange_token.py` to swap for a long-lived (~60-day) token via `GET /oauth/access_token?grant_type=fb_exchange_token` (needs `META_APP_ID` + `META_APP_SECRET`).
- App is on Marketing API `development_access` tier: restricted to ad accounts of users with an app role (the founder — fine) + lower rate limits (irrelevant at our volume). Standard Access/App Review remains the Phase B gate only.
- `read_insights` already grantable → Phase C metrics need no review for the founder account.
- **Sandbox Ad Account** (1 allowed on dev tier): use as verification step zero — run the full campaign→adset→ad flow with zero spend risk before touching the real account. Sandbox doesn't deliver ads and has creative-upload quirks, so the real-account PAUSED test remains step two. `META_AD_ACCOUNT_ID` env switches between sandbox and real account.

**New files** (in `ignite-ads/`):
- `backend/services/ads_service/base.py` — `AdsPlatform` ABC + `LaunchSpec` model
- `backend/services/ads_service/meta_platform.py` — the core client:
  - Upload: `POST /{account_id}/advideos` with `file_url=<public video URL>` (no download); poll video status until ready (~5 min timeout, backoff)
  - Creative: `POST /{account_id}/adcreatives` with `object_story_spec.video_data` (video_id, thumbnail from `/{video_id}/thumbnails`, message/title/CTA/link)
  - Campaign (`OUTCOME_TRAFFIC`/`OUTCOME_SALES`, PAUSED) → AdSet (daily_budget, `IMPRESSIONS` billing, `LINK_CLICKS` goal, targeting, PAUSED) → Ad (creative, PAUSED)
  - Each step persists ids to `ad_campaigns.platform_ids` via callback; launch re-reads doc and skips completed steps (idempotent resume)
  - Graph errors surfaced (`code`, `error_user_msg`) into `ad_campaigns.error`
- `backend/services/ads_service/factory.py` — `AdsFactory.get_platform("meta")`
- `backend/services/ads_service/ai_copy.py` — `generate_ad_copy(video_meta, brand_doc)` via Gemini (port the minimal LLM-JSON helper from IgniteAI's `engine/llm_factory.py`); inputs: run script (if `source_run_id`) + brand kit from shared `brands/{user_id}`
- `backend/services/ads_service/cost.py` — `charge_ad_launch(...)` — THE cost hook; returns 0 today; deducts from shared `user_credits` when monetized
- `backend/services/db_service.py` — ad account/launch CRUD (transactional `create_ad_launch` keyed on `launch_id`), read-only `get_execution_video_url(run_id)`
- `scripts/ads/exchange_token.py` — exchange short-lived token (from the Meta dev console tool) for a long-lived one; prints expiry
- `scripts/ads/launch_meta_ad.py` — CLI: `--run-id | --video-url`, `--daily-budget-cents --landing-url [--ai-copy] [--countries] [--activate]`; `--activate` is a separate explicit invocation, never default
- `scripts/ads/sync_meta_status.py` — refresh effective/review status for all launches
- `directives/launch_meta_ad.md` — SOP: preconditions, budget cap, PAUSED-first, human confirm before activate, Ads Manager verification checklist

**Env vars**: `META_APP_ID`, `META_APP_SECRET` (for token exchange), `META_ACCESS_TOKEN` (long-lived), `META_AD_ACCOUNT_ID` (sandbox or real `act_...`), `META_PAGE_ID`, `META_GRAPH_API_VERSION`, `ADS_MAX_DAILY_BUDGET_CENTS`, `FIREBASE_*`/ADC creds. `.env` local; `.config/cloud-run-env.yaml` for deploys.

**Deps**: `fastapi`, `uvicorn`, `requests`, `firebase-admin`, `google-cloud-firestore`, `google-cloud-tasks`, `google-genai` (ai_copy), `pydantic`. `cryptography` only in Phase B.

**Verification ladder**: (0) token/page dry checks (`GET /me/adaccounts`, `GET /{page_id}`); (1) full launch flow against the **sandbox ad account** — zero spend risk; (2) PAUSED campaign at $1/day on the real account for a completed IgniteAI run → verify in Ads Manager (structure, video plays, CTA, link) + Firestore doc completeness; (3) kill mid-launch and re-run → resumes without duplicates; (4) one 24h min-budget real activation, confirm delivery, pause.

## Phase B — Multi-tenant self-serve SaaS

**Submit Meta App Review at Phase A start** (`ads_management`, `ads_read`, `pages_show_list`, `business_management` + FB Login for Business + Business Verification) — 2–6 weeks; use Phase A screencasts. Decide then whether to upgrade the existing "My Insta Manager" app to Standard Access or create a clean, product-branded app for review (recommended: dedicated app, since review scrutinizes app name/branding/use-case coherence; only env vars change).

**Backend** — `backend/routers/`:
- `accounts.py` — OAuth start (CSRF state doc) / callback (code → long-lived token → account+page picker → Fernet-encrypt → `ad_accounts`); list/disconnect
- `campaigns.py` — `POST /copy-suggest`; `POST /launch` (auth + ownership + budget cap + cost hook + idempotent create + Cloud Tasks enqueue, BackgroundTasks fallback); `GET /campaigns[/{id}]`; `POST /campaigns/{id}/activate` (requires `confirm: true`) / `pause`; `POST /task/run` Cloud Tasks handler (validate `X-CloudTasks-QueueName`, resume idempotently)
- Token expiry: <7 days → mark `expired`, 409 "reconnect required"

**Frontend** — scaffold Angular app (mirror IgniteAI patterns: standalone components, auth interceptor with Firebase ID token, service-based state): connect-account flow, launch wizard (budget, schedule, landing URL, editable AI copy, "publishes PAUSED" notice), campaigns dashboard with activate/pause confirm.

**IgniteAI cross-link** (small change in the existing repo, later): "Launch as Ad" button in the completion modal/library deep-links to the ads app with `run_id` — same Firebase session works across both apps.

**Verification**: OAuth-connect a second non-founder Meta account; UI launch lands PAUSED in that account's Ads Manager; ownership isolation; forced mid-launch 500 → Cloud Tasks retry resumes without duplicates.

## Phase C — Performance metrics

- `backend/routers/metrics.py`: `POST /task/sync-metrics` (Cloud Scheduler target, OIDC SA auth) — iterate active/paused campaigns, `GET /{ad_id}/insights?fields=impressions,clicks,ctr,spend,actions&time_increment=1` → daily `metrics/` docs + `lifetime` rollup; detect `DISAPPROVED` → `status="rejected"` + notification. `GET /campaigns/{id}/metrics?days=30`.
- Cloud Scheduler job every 6h (setup documented in module docstring + deploy script).
- Frontend: metric columns + per-campaign daily chart (inline SVG/CSS bars, no chart lib).

**Verification**: manual `curl` sync against the Phase A live campaign; numbers match Ads Manager.

## Phase D — Creative iteration loop (sketch only)

`ai_iteration.py`: LLM classifies winners/losers from metrics, proposes variant briefs (new hooks, same product) → pre-fills an IgniteAI generation request (deep-link or API call back to IgniteAI). Internal-first via directive + `scripts/ads/propose_iterations.py`; productize later as `POST /campaigns/{id}/iterate`. Closes the loop: generate → launch → measure → regenerate.

## Risks

- **Meta App Review timeline** (Phase B only) — submit at Phase A start
- **Token expiry** (~60-day long-lived tokens, no silent refresh) — reconnect UX; system-user token via Business Manager as future alternative
- **Ad policy rejections** on AI-generated UGC — PAUSED-by-default + review-status sync
- **Double-launch on retries** — the key correctness invariant; step-resume state machine, tested explicitly
- **Budget minimums** (currency-dependent ~$1/day) — validate against account currency
- **Video URL must be publicly fetchable** by Meta for `file_url` upload — IgniteAI GCS URLs are public today; revisit if they become signed
- **Shared-Firestore blast radius** — ads app writes only `ad_*` collections; `executions`/`brands`/`user_credits` access is read-only (except credit deduction via the cost hook when enabled)
