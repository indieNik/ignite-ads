# Directive: Launch a Meta Ad from a Generated Video

Take a completed UGC video (IgniteAI run or any public video URL) to a **PAUSED**
Meta campaign on the founder's ad account, verify it, and only then — with
explicit human confirmation — activate it.

## Preconditions

1. `.env` has: `META_ACCESS_TOKEN` (long-lived), `META_AD_ACCOUNT_ID`, `META_PAGE_ID`,
   `META_APP_ID`, `META_APP_SECRET`. If the token is expired/missing, get a fresh
   short-lived token from the Meta dev console (Marketing API → Tools → Get Token,
   permissions: ads_management, ads_read, read_insights) and run:
   `python scripts/ads/exchange_token.py --token <SHORT_TOKEN>`
2. The creative exists: either an IgniteAI `run_id` with `status=completed`, or a
   publicly fetchable video URL.
3. Budget respects the cap (`ADS_MAX_DAILY_BUDGET_CENTS`, default 50000 minor units).
4. The user has approved the landing URL and budget for this specific launch.

## Procedure

1. **Dry check** (always run first in a new session):
   `python scripts/ads/launch_meta_ad.py --check`
2. **Launch PAUSED**:
   `python scripts/ads/launch_meta_ad.py --run-id <RUN_ID> --daily-budget-cents <N> --landing-url <URL> --ai-copy`
   - `--ai-copy` prints a Gemini suggestion and asks for confirmation; pass
     `--primary-text/--headline` instead for manual copy.
   - **A/B test**: add `--num-variants {2,3}` (with `--ai-copy`) — one video
     becomes N ads with different copy inside ONE adset sharing ONE budget.
     For a fair test scale the budget ≈ ₹100 × variants; Meta auto-favors one
     ad early at thin budgets.
   - Use `--video-url` instead of `--run-id` for non-IgniteAI creatives.
3. **Verify in Ads Manager** (the script prints a direct link):
   - Campaign, ad set, and ad all exist and are PAUSED
   - Video plays; thumbnail sensible; CTA + landing URL correct
   - Copy reads correctly; no policy red flags (personal attributes, claims)
4. **Sync review status** after Meta reviews (usually minutes–hours):
   `python scripts/ads/sync_meta_status.py`
   - `DISAPPROVED` → read the feedback in the output, fix the creative/copy, relaunch.
5. **Activate** — only after the user explicitly confirms spend:
   `python scripts/ads/launch_meta_ad.py --activate --launch-id <LAUNCH_ID>`
   (requires typing ACTIVATE interactively — never bypass this.)
6. **Monitor**: `python scripts/ads/sync_meta_status.py --insights`
7. **Pause**: `python scripts/ads/launch_meta_ad.py --pause --launch-id <LAUNCH_ID>`

## Edge cases & learnings

- **Error 200 "Ad account has no access to this Instagram account"** (at creative
  step): the Page has no usable Instagram identity. Meta validates an IG actor on
  video creatives even for Facebook-only placements. Fix: the client auto-resolves
  via `ensure_instagram_actor()` (linked IG → existing PBIA → create PBIA), but
  PBIA creation needs the token to ALSO have `pages_read_engagement` — regenerate
  the token with that permission and re-exchange if you see this error.
- **Error 100 "Param instagram_actor_id must be a valid Instagram account id"**:
  v23 rejects the legacy `instagram_actor_id` field — pass the IG/PBIA id as
  `object_story_spec.instagram_user_id` instead (validated 2026-06-11).
- **Error 100 "is_adset_budget_sharing_enabled"**: newer Graph versions require
  this field on campaigns when budget lives on the ad set (we send `False`).
- **`video_feeds` Facebook position is deprecated** — don't request it; default
  (Advantage+) placements are fine once an IG actor exists.

- **Interrupted launch** (network error, ^C): the launch doc keeps per-step
  `platform_ids`. Resume with `--resume --launch-id <LAUNCH_ID>` — completed
  steps are skipped, nothing is duplicated. Never start a fresh launch for the
  same intent without checking `ad_campaigns` for an existing doc first.
  (Validated 2026-06-12 with a 3-variant launch killed after ad v1: resume
  skipped all 6 completed steps and created only the missing objects.)
- **Multi-variant platform_ids**: indexed keys `creative_id_0..2`/`ad_id_0..2`;
  the singular `ad_id`/`creative_id` on a doc are legacy aliases = variant 0.
  Read code goes through `get_ad_entries()`/`get_copy_variants()` in
  `backend/services/ads_service/base.py` — never parse the dict by hand.
- **Video processing timeout**: Meta processes the uploaded video async; the
  script polls up to 5 min. Large/4K files can exceed this — just `--resume`.
- **Error 400 with OAuth code 190**: token expired → re-run the token exchange.
- **"Requires image_url"**: Meta needs a thumbnail for video creatives; the
  script auto-fetches Meta's generated thumbnails, which can lag right after
  upload. `--resume` after a minute usually fixes it.
- **Sandbox account**: set `META_AD_ACCOUNT_ID` to the sandbox account id to
  test the flow with zero spend risk (sandbox can't deliver and sometimes
  rejects `file_url` uploads — real-account PAUSED is the true test).
- **Never** set an ad ACTIVE through any path other than `--activate`.
