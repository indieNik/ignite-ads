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

### Verification ladder progress (2026-06-11)
1. ~~Fill `.env`~~ ✅ All values set. Founder UID `rYiUmqEJs6P182fiUR2Vx7SXaEA3` (Firebase account is niki.thrill@gmail.com — NOT the professional address). `FIREBASE_SERVICE_ACCOUNT_PATH` points (absolute) at IgniteAI's service-account.json.
2. ~~`--check` dry checks~~ ✅ PASSED. Token OK. Ad accounts visible: act_308400644 (Nikhil Patil), act_278753666454205 (Nik Ads), act_719968544441517 (Tea Tee Store Ad — currently selected in .env). Page: Gitolx (721068071348640). **Account currency is INR → daily_budget_cents is PAISE; Meta's INR minimum daily budget ≈ ₹85+, so use ≥10000 (₹100) for tests, not 100.**
3. (Optional) sandbox account test — skipped/available, 1 allowed on dev tier
4. **← NEXT: first real PAUSED launch.** Founder has 115 completed runs; latest: `run_bbd287a971114219945b96e990dcb529` (2026-06-07). Awaiting founder's choice of run + landing URL, then:
   `python scripts/ads/launch_meta_ad.py --run-id <RUN> --daily-budget-cents 10000 --landing-url <URL> --ai-copy` → verify in Ads Manager
5. Idempotency test: kill mid-launch, `--resume --launch-id <id>` → no duplicates
6. One 24h min-budget activation (`--activate`, typed confirm) → confirm delivery → `--pause`
7. Update this file + directive with learnings (real Meta errors, timing)

Gotcha log: `executions` queries combining where(user_id)+order_by(created_at) need a composite Firestore index that doesn't exist — filter/sort client-side (see db_service usage).

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
