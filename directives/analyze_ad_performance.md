# Directive: Analyze Ad Performance (MongoDB MCP)

Classify running/finished campaigns into winners and losers using the metrics
in MongoDB Atlas, and propose creative-iteration briefs. This is the analysis
half of the Phase D loop: generate → launch → measure → **analyze → iterate**.

## Why MongoDB + MCP here

Firestore is the *operational* store (launch state machine, tokens). Metrics
are mirrored into MongoDB Atlas (`igniteads` db) by the sync paths so the
agent can query/aggregate them **directly via the MongoDB MCP server** —
flexible aggregations without writing one-off backend endpoints. The server is
configured in `.mcp.json` (read-only) and reads `MONGODB_URI` from the
environment.

## Data model (db: `igniteads`)

- `metrics_daily` — one doc per (launch_id, date): impressions, clicks, ctr,
  spend, headline, user_id, synced_at
- `campaign_summaries` — one doc per launch: lifetime impressions/clicks/spend,
  status, review_status, headline, primary_text, budget, landing_url,
  source_run_id

Data freshness: docs are written on every `/api/ads/campaigns/{id}/sync` and
`scripts/ads/sync_meta_status.py --insights` run. Sync first if data is stale.

## Procedure

1. Ensure fresh data: `python scripts/ads/sync_meta_status.py --insights`
2. Using the MongoDB MCP tools (e.g. `aggregate` on `campaign_summaries`):
   - Compute CTR (`clicks / impressions`) and CPC (`spend / clicks`) per campaign;
     ignore campaigns with `impressions < 500` (not enough signal).
   - **Winners**: top quartile CTR AND CPC below the account median.
   - **Losers**: bottom quartile CTR with spend > 0, or `review_status` DISAPPROVED.
3. For each winner, propose 2–3 iteration briefs: same product + landing URL,
   new hook angles derived from the winning `headline`/`primary_text` (use the
   `source_run_id` to pull the original video script from IgniteAI's
   `executions` for context).
4. Present the briefs to the founder. On approval, feed each brief into
   IgniteAI generation, then launch the new variant via
   `directives/launch_meta_ad.md` (PAUSED-first as always).

## Edge cases

- `MONGODB_URI` unset → the analytics mirror is disabled (sync still works,
  Firestore only). Ask the founder for the Atlas connection string.
- The MCP server is `--readOnly` by design — writes only ever come from the
  deterministic sync paths, never from agent improvisation.
- Zero-impression campaigns (never activated) are launch successes but carry
  no performance signal — exclude from analysis, don't call them losers.
