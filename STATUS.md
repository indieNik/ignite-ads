# STATUS — IgniteAds session-resume tracker

> **Agents: read this first, update it last.** Keep entries terse; newest phase state at top.
> Full plan: `docs/PLAN.md`. Operating rules: `CLAUDE.md`.

## Current state (2026-06-11)

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

### Next (Phase A verification ladder — needs founder credentials)
1. Fill `.env`: `META_APP_ID`, `META_APP_SECRET` (dev console → App settings → Basic, app "My Insta Manager" id 2140108452878655), short-lived token from Marketing API → Tools → Get Token → run `python scripts/ads/exchange_token.py --token <T>` → paste `META_ACCESS_TOKEN`. Set `META_AD_ACCOUNT_ID`, `META_PAGE_ID`, Firebase creds (same values as IgniteAI `.env`), `GEMINI_API_KEY`.
2. `python scripts/ads/launch_meta_ad.py --check` (token/account/page dry checks)
3. Optional: sandbox account test (create in dev console → set `META_AD_ACCOUNT_ID` to sandbox id)
4. Real PAUSED launch at minimal budget: `--run-id <completed IgniteAI run> --daily-budget-cents 100 --landing-url <URL> --ai-copy` → verify in Ads Manager
5. Idempotency test: kill mid-launch, `--resume --launch-id <id>` → no duplicates
6. One 24h min-budget activation (`--activate`, typed confirm) → confirm delivery → `--pause`
7. Update this file + directive with learnings (real Meta errors, timing)

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
