# STATUS — IgniteAds session-resume tracker

> **Agents: read this first, update it last.** Keep entries terse; newest phase state at top.
> Full plan: `docs/PLAN.md`. Operating rules: `CLAUDE.md`.

## Current state (2026-06-12, later) — MongoDB MCP + UI polish

- **MongoDB MCP integration shipped** (Rapid Agent hackathon partner requirement): `backend/services/metrics_store.py` mirrors metrics to Atlas (`igniteads.metrics_daily` + `campaign_summaries`) from both sync paths; `.mcp.json` runs the official mongodb-mcp-server read-only; `directives/analyze_ad_performance.md` is the agent SOP for winner/loser analysis. **Founder action: create free Atlas cluster, paste `MONGODB_URI` into `.env` AND `.config/cloud-run-env.yaml`, redeploy backend.** Code no-ops gracefully without it.
- UI: launch modal got real loading states (Gemini button gradient-border spinner, field shimmer, typewriter copy reveal, launching state).
- Repo is PUBLIC (MIT). Rapid Agent hackathon SUBMITTED (video: https://www.youtube.com/watch?v=3RMfih-jVuk). Architecture diagram at docs/architecture.png.

## Earlier (2026-06-12) — DEPLOYED TO PRODUCTION

**Full stack live for hackathon submissions:**
- **Backend**: https://ignite-ads-backend-928660012632.us-central1.run.app (Cloud Run `ignite-ads-backend` in `instagram-content-bot-479808` — same free-credit project as IgniteAI; Firebase creds passed via `FIREBASE_SERVICE_ACCOUNT_JSON` env, NOT a baked file). Routes: /api/ads/{runs,campaigns,launch,copy-suggest,task/run,campaigns/{id}/{activate,pause,sync}}.
- **Frontend**: https://igniteai-ads.web.app (Firebase Hosting site `igniteai-ads` in `ignite-ai-01`). Angular 20 single-component dashboard: Google sign-in, campaign cards, launch form with Gemini copy-suggest, activate (confirm) / pause / sync. Deploy: `bash scripts/deploy/deploy-frontend.sh`.
- **Custom domain** ads.igniteai.in: NOT yet connected — founder must add it in Firebase console (Hosting → igniteai-ads → Add custom domain) + DNS record. Domain pre-authorized in Firebase Auth.
- **Account split gotcha**: three different Google accounts — gcloud deploys (`GCP_ACCOUNT`, Cloud Run project), firebase deploys (`FIREBASE_DEPLOY_ACCOUNT`, owns ignite-ai-01), and the founder app-login user. All recorded in gitignored `.config/gcp.env`. Auth authorized domains updated via Identity Toolkit API + SA.
- **E2E verified in prod** (custom-token test): auth ✅, campaigns list ✅, 50 runs ✅, Meta sync ✅ — first launch passed Meta review (effective_status PAUSED, was IN_PROCESS).
- **Devpost docs**: `docs/devpost/STARTUPS_AI_AGENTS_CHALLENGE.md` + `RAPID_AGENT_HACKATHON.md` (read the qualification-gaps section — public repo + LICENSE + partner MCP needed for the consumer one).

## Earlier state (2026-06-11)

**Phase A scaffold COMPLETE — code written, NOT yet run against Meta.**
Built in a single session from the approved plan (plan copied to `docs/PLAN.md`).

### Done
- [x] Repo scaffolded; infra ported from IgniteAI (firebase_setup, dependencies, logger, cloud_tasks_service)
- [x] `AdsPlatform` ABC + `MetaAdsPlatform` (raw Graph API, step-resume state machine, PAUSED-first)
- [x] `AdsFactory`, `ai_copy.py` (Gemini), `cost.py` hook (charges 0), `db_service.py` (ad_* CRUD, idempotent create, read-only IgniteAI views)
- [x] CLI: `exchange_token.py`, `launch_meta_ad.py` (--check/--ai-copy/--resume/--activate/--pause), `sync_meta_status.py`
- [x] Directive `directives/launch_meta_ad.md`
- [x] Deploy scripts (Cloud Build only — founder's machine cannot run Docker)
- [x] All modules py_compile-verified; CLI --help smoke-tested
- [x] git repo initialized, pushed to GitHub (`indieNik/ignite-ads`, private)

### Verification ladder progress (2026-06-11)
1. ~~Fill `.env`~~ ✅ All values set. Founder UID `rYiUmqEJs6P182fiUR2Vx7SXaEA3` (the personal-Gmail Firebase account, NOT the professional address — see `FOUNDER_USER_ID` in `.env`). `FIREBASE_SERVICE_ACCOUNT_PATH` points (absolute) at IgniteAI's service-account.json.
2. ~~`--check` dry checks~~ ✅ PASSED. Token OK. Ad accounts visible: act_308400644 (Nikhil Patil), act_278753666454205 (Nik Ads), act_719968544441517 (Tea Tee Store Ad — currently selected in .env). Page: Gitolx (721068071348640). **Account currency is INR → daily_budget_cents is PAISE; Meta's INR minimum daily budget ≈ ₹85+, so use ≥10000 (₹100) for tests, not 100.**
3. (Optional) sandbox account test — skipped/available, 1 allowed on dev tier
4. ~~First PAUSED launch~~ ✅ **COMPLETE** (`adl_60737a55f918484f8240e954629262d6`, run `run_bbd287a971114219945b96e990dcb529`, ₹100/day, landing igniteai.in). Full chain on act_719968544441517: video 780954251680077 → creative 2089773941964193 → campaign 120248873448810548 → adset 120248873451870548 → ad 120248873454940548. All PAUSED; review_status IN_PROCESS after first sync. Took 3 fixes across 3 resume cycles (see gotcha log) — which also de-facto validated step-resume idempotency (steps correctly skipped on every resume). Founder should eyeball it in Ads Manager.
5. Idempotency test: kill mid-launch, `--resume --launch-id <id>` → no duplicates
6. One 24h min-budget activation (`--activate`, typed confirm) → confirm delivery → `--pause`
7. Update this file + directive with learnings (real Meta errors, timing)

Gotcha log:
- Firestore: ANY where()+order_by() combo needs a composite index the shared project doesn't have — always filter/sort client-side (fixed in `list_ad_launches`).
- Meta: token from dev console "Get Token" can be blocked by browser extensions (CSP errors) — use Graph API Explorer instead.
- Meta: video creatives REQUIRE an IG identity even for fb-only placements. Page had no linked IG → use page-backed IG account (PBIA); needs `pages_read_engagement` on the token. **Field is `instagram_user_id` — `instagram_actor_id` is rejected on v23.**
- Meta: campaigns need `is_adset_budget_sharing_enabled` when budget is on the adset; `video_feeds` FB position is deprecated.
- Meta: INR account → `daily_budget_cents` = paise; min daily ≈ ₹85+.

### After Phase A validates
- Submit Meta App Review (Phase B gate, 2–6 weeks — start early; see docs/PLAN.md)
- Phase B: routers (OAuth accounts, launch endpoints), Angular frontend, Fernet token storage
- Phase C: metrics sync (Cloud Scheduler), dashboard
- Phase D: creative iteration loop back into IgniteAI

## Decisions log
- 2026-06-11: Standalone repo, shared Firebase/GCP project (`ignite-ai-01`); FastAPI+Angular mirror stack; Meta first; monetization deferred (cost hook stubbed at 0); raw Graph API over facebook_business SDK; MCP only for read-only inspection, launches via deterministic Python.
- 2026-06-11: No local Docker on founder's machine — Cloud Build deploys only.

## Open questions
- Founder user_id for `ad_accounts` doc: currently `FOUNDER_USER_ID` env (defaults to "founder"). Set it to the real Firebase UID so launches show up under the founder's account in Phase B UI.
- Sandbox account not yet created in dev console (1 allowed on dev tier).
