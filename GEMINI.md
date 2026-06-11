# Agent Instructions — IgniteAds

> Mirrored across CLAUDE.md, AGENTS.md, and GEMINI.md so the same instructions load in any AI environment.

**Resume protocol: read `STATUS.md` FIRST in every new session.** It tracks exactly where work stopped, what's verified, and what's next. Keep it updated whenever you finish or hand off work — it is the cross-session memory for this repo.

## What this project is

IgniteAds takes AI-generated UGC video ads (from the sibling IgniteAI repo at `../AI UGC Ad Video Builder`, or any public video URL) and **actually launches them as ads** — Meta (Facebook/Instagram) first, Google Ads later. It closes the loop: generate → launch → measure → iterate.

**Standalone codebase, shared infra**: same Firebase/GCP project as IgniteAI (`ignite-ai-01`) — shared Auth users, shared Firestore, shared GCS. This service writes ONLY `ad_*` collections (`ad_accounts`, `ad_campaigns`); `executions`, `brands`, `user_credits` are read-only (except the credit cost hook when monetization lands).

Full plan + phase details: `docs/PLAN.md`. Current state: `STATUS.md`.

## 3-Layer Architecture (same operating model as IgniteAI)

1. **Directives** (`directives/`): SOPs in Markdown — goals, inputs, scripts, edge cases.
2. **Orchestration**: you. Read directives, call scripts in order, handle errors, ask when unsure, update directives with learnings (self-anneal).
3. **Execution** (`backend/`, `scripts/`): deterministic Python. API calls, Firestore, file ops live here — never improvised by the agent.

## Layout

```
backend/                 # FastAPI (Cloud Run service: ignite-ads-backend)
  main.py                # app shell; Phase B routers register here
  dependencies.py        # get_current_user (Firebase ID token, shared project)
  firebase_setup.py      # Firebase Admin init (env JSON / cred path / ADC)
  services/
    db_service.py        # ads_db singleton — ad_* CRUD + read-only IgniteAI views
    cloud_tasks_service.py  # Phase B async launches (queue: ignite-ads-jobs)
    ads_service/
      base.py            # AdsPlatform ABC + LaunchSpec/AdCopy/LaunchConfig models
      meta_platform.py   # Meta Graph API client (raw requests, version-pinned)
      factory.py         # AdsFactory.get_platform("meta")
      ai_copy.py         # Gemini ad-copy suggestions (policy-safe prompt)
      cost.py            # THE monetization hook (returns 0 today)
scripts/ads/             # Phase A CLI: launch_meta_ad.py, sync_meta_status.py, exchange_token.py
scripts/deploy/          # Cloud Build deploys — NEVER run docker locally
directives/              # launch_meta_ad.md SOP
.config/                 # gcp.env + cloud-run-env.yaml (GITIGNORED; .example templates committed)
```

## Critical invariants (do not break)

- **PAUSED-first**: every campaign/adset/ad is created `PAUSED`. The ONLY activation path is `launch_meta_ad.py --activate` with typed interactive confirmation. Never default-activate, never bypass.
- **Budget cap**: validate `daily_budget_cents <= ADS_MAX_DAILY_BUDGET_CENTS` before any launch.
- **Idempotent launches**: `launch_id` (`adl_<uuid>`) is the idempotency key. Each Graph API step persists its id to `ad_campaigns.platform_ids` before the next step; resume re-reads the doc and skips completed steps. Never reorder steps without preserving this.
- **Graph API version** is pinned in ONE place: `META_GRAPH_API_VERSION` env (read in `meta_platform.py`). No version strings anywhere else.
- **Token never in Firestore for Phase A**: founder token lives in `.env` (`token: {type: "env"}` descriptor). Phase B customer tokens are Fernet-encrypted (`ADS_TOKEN_ENC_KEY`).
- **Firestore transactions**: use the `@firestore.transactional` decorator pattern (see `db_service.create_ad_launch`), not `@db.transaction()`.
- **Shared-Firestore blast radius**: never write to IgniteAI collections from this repo.
- **No local Docker — ever.** The founder's machine cannot run Docker. Deploys go through `scripts/deploy/deploy-backend.sh` (Cloud Build via `gcloud run deploy --source .`). The Dockerfile is for Cloud Build only.

## Meta API gotchas (learned/expected)

- Dev-console tokens are short-lived → exchange via `scripts/ads/exchange_token.py` (~60-day token). Expired token = OAuth error code 190.
- App is on Marketing API `development_access` tier: only ad accounts of app-role users work; fine for Phase A. Standard Access (App Review) is the Phase B gate.
- Video creatives REQUIRE a thumbnail `image_url`; Meta's auto-thumbnails can lag right after upload — `--resume` after a minute.
- Ad sets on newer Graph versions require explicit `targeting_automation.advantage_audience` (we send 0).
- `file_url` upload needs the video URL publicly fetchable by Meta (IgniteAI GCS URLs are public).
- Effective status lives on the AD object (`effective_status`); rejection detail in `ad_review_feedback`.

## Git & deployment workflow (IgniteAI conventions)

- Work on dated feature branches (e.g. `meta-launch-11-Jun-2026`); never commit directly to `main`.
- Ship: commit → push branch → `gh pr create` → merge → deploy from `main`.
- Deploys ONLY via `scripts/deploy/*.sh` (Cloud Build remote builds). Raw `gcloud run deploy`/`firebase deploy` and any local `docker` command are forbidden.
- `.config/gcp.env` (gitignored) is the single source of truth for GCP target (`SERVICE_NAME=ignite-ads-backend`).

## Local dev

```
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # fill Meta + Firebase values
python scripts/ads/launch_meta_ad.py --check     # dry checks
uvicorn backend.main:app --port 8001             # API shell (Phase B)
```
