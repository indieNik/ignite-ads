# Devpost Submission — Google Cloud Rapid Agent Hackathon
> Portal: devpost.com/submit-to/29711 (submission #1047752) · "Building agents for real-world challenges"
> Judging: Technological Implementation · Design · Potential Impact · Quality of the Idea
> ⚠️ **Qualification gaps — read first** (bottom of this doc): public repo + license, partner MCP integration, 3-min video.

---

## Project overview (step 2)

**Project name** *(≤60 chars)*
```
IgniteAds — AI agent that launches your ads, not just writes them
```
*(58 chars. Shorter alt: `IgniteAds — the agent that runs your ads` — 41 chars)*

**Elevator pitch** *(≤200 chars)*
```
An autonomous media-buying agent: give it a product video, it writes the copy with Gemini, builds the whole Meta campaign, launches it PAUSED, and reports performance. You just say ACTIVATE.
```
*(192 chars)*

## Project details (step 3)

### About the project
*(paste into "About the project" — Markdown supported)*

```markdown
## Inspiration
Every small business owner we know has the same dead-end folder: marketing videos they made (or AI made for them) that never became actual ads. Ads Manager is a part-time job — uploading, copywriting, campaign/ad-set/ad hierarchies, placements, review states, budgets. Agents shouldn't just answer questions about ads; they should *run* them.

## What it does
IgniteAds is a task-completing agent, not a chatbot. One mission — "launch this video as an ad" — becomes a fully autonomous multi-step plan:
1. Pulls the video + its generation script from our creative platform (or any video URL)
2. **Gemini 2.5 Flash** writes policy-safe ad copy (primary text / headline / description) grounded in the video script + brand kit
3. Resolves the Meta identity chain — page, Instagram actor, auto-creating a page-backed Instagram account when none exists
4. Builds the full chain on the Meta Marketing API: video upload → creative → campaign → ad set → ad
5. Launches **everything PAUSED** — the human gives one typed `ACTIVATE` to start spend
6. Monitors review status and pulls daily Insights (impressions, clicks, CTR, spend) back into the loop

## How we built it
- **3-layer agent architecture**: markdown directives (SOPs) → agent orchestration → deterministic Python tools. The LLM never improvises an API call; it decides, deterministic code executes.
- **Idempotent step-resume state machine**: each Graph API step persists its platform ID to Firestore *before* the next step. Interrupt it anywhere and resume — zero duplicates, zero double spend. Our first production launch survived 2 failures and 3 resume cycles and completed cleanly.
- **Google Cloud**: Cloud Run (FastAPI), Firestore (multi-tenant launch state), Cloud Tasks (durable async), Firebase Auth + Hosting (Angular dashboard), Cloud Build deploys, Gemini for copy.
- **Guardrails for an agent that spends money**: PAUSED-first, hard budget caps, typed human confirmation for activation, full Graph API audit log.

## Challenges we ran into
The Meta API's real surface diverges from its docs — all found in ONE live launch: video creatives require an Instagram actor even for Facebook-only placements; Graph v23 renamed `instagram_actor_id` → `instagram_user_id` without fanfare; campaigns now require `is_adset_budget_sharing_enabled`. Our self-annealing loop (fix the tool → update the directive → the agent never hits it again) turned each failure into permanent knowledge.

## Accomplishments we're proud of
A real, verifiable launch: our agent created a live (paused) campaign — video, creative, campaign, ad set, ad — on a real Meta ad account, visible in Ads Manager, in under 2 minutes of agent time.

## What we learned
Idempotency is the most important property of an agent with a wallet. And PAUSED-first is the right trust contract between humans and autonomous systems: the agent does 100% of the work; the human spends one word of attention exactly where it matters.

## What's next
Multi-tenant OAuth (Meta App Review in progress), Google Ads as a second platform behind the same abstraction, and the full closed loop: performance data → Gemini proposes new creative variants → auto-generate → relaunch.
```

### Built with
```
gemini, google-cloud-run, cloud-firestore, google-cloud-tasks, firebase-auth, firebase-hosting, cloud-build, python, fastapi, angular, typescript, meta-marketing-api, mcp
```

### "Try it out" links
- https://ads.igniteai.in — hosted dashboard (Google sign-in)
- https://github.com/indieNik/ignite-ads — source *(must be public + licensed, see gaps)*

### Video demo link
*(YouTube — record with the 3-min script in `STARTUPS_AI_AGENTS_CHALLENGE.md`; same video works for both submissions)*

---

## ⚠️ Qualification gaps & fastest fixes

1. **Public open-source repo with license** — repo is currently **private** and has **no LICENSE**.
   Fix (2 min): add MIT or Apache-2.0 `LICENSE` file, then `gh repo edit indieNik/ignite-ads --visibility public`. ⚠️ Verify no secrets in git history first (we kept `.env`/`.config` gitignored from commit zero, so history is clean — but eyeball `git log --stat` before flipping).
2. **Partner MCP server integration** — this hackathon's prize buckets require a *meaningful* integration with ONE partner: Arize, Elastic, Fivetran, GitLab, **MongoDB**, Dynatrace.
   **Recommendation: MongoDB.** Smallest honest integration that's genuinely useful: store ad-performance metric snapshots in MongoDB Atlas and let the agent query/aggregate them through the **MongoDB MCP server** (winner/loser analysis across campaigns — the input to our creative-iteration loop). Estimated: a free Atlas cluster + ~1 hour of agent-side wiring. Pick the **MongoDB bucket** on the submit form if we do this; otherwise this submission risks disqualification on the "Partner Power" requirement.
3. **~3 minute demo video** — required; record once, reuse for both challenges.
4. **Google Cloud Agent Builder** is named in "How to Build" — our build is Gemini-on-Cloud-Run rather than Agent Builder low-code. The requirements say "powered by Gemini and Google Cloud" — we qualify via Gemini + GCP stack, but if time permits, mentioning an ADK/Agent Builder wrapper in "What's next" softens this.

## Submit-form checklist
- [ ] Track/bucket: **MongoDB** (if integration done) — else pick closest and disclose
- [ ] Hosted project URL: https://ads.igniteai.in
- [ ] Public repo URL with LICENSE visible in About
- [ ] Video URL (YouTube, ≤3 min)
- [ ] Thumbnail: use a frame of the ad preview grid (5MB max, 3:2)
- [ ] Image gallery: Ads Manager screenshot (paused campaign), advanced-preview grid, architecture diagram
```
