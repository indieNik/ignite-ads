#!/usr/bin/env python3
"""
Phase A launcher — take a generated video to a PAUSED Meta ad campaign.

Everything is created PAUSED. Activation is a separate, explicit invocation
(--activate --launch-id ...) that asks for typed confirmation. See
directives/launch_meta_ad.md for the full SOP.

Examples:
  # Dry checks only (token, ad account, page)
  python scripts/ads/launch_meta_ad.py --check

  # Launch from an IgniteAI run, AI-suggested copy, $1/day, PAUSED
  python scripts/ads/launch_meta_ad.py --run-id run_abc123 \\
      --daily-budget-cents 100 --landing-url https://example.com --ai-copy

  # A/B test: one video, 3 ads with different Gemini copy in one adset
  python scripts/ads/launch_meta_ad.py --run-id run_abc123 \\
      --daily-budget-cents 30000 --landing-url https://example.com \\
      --ai-copy --num-variants 3

  # Launch any public video URL with manual copy
  python scripts/ads/launch_meta_ad.py --video-url https://storage.googleapis.com/.../ad.mp4 \\
      --daily-budget-cents 100 --landing-url https://example.com \\
      --primary-text "..." --headline "..."

  # Resume an interrupted launch (idempotent — completed steps are skipped)
  python scripts/ads/launch_meta_ad.py --resume --launch-id adl_xxx

  # Activate (the ONLY way an ad goes live)
  python scripts/ads/launch_meta_ad.py --activate --launch-id adl_xxx
"""
import argparse
import os
import sys

from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from backend.logger import get_logger  # noqa: E402
from backend.services.ads_service import (AdCopy, AdsFactory, LaunchConfig, LaunchSpec,  # noqa: E402
                                          Targeting, get_copy_variants)
from backend.services.ads_service.cost import charge_ad_launch  # noqa: E402
from backend.services.db_service import ads_db, new_launch_id  # noqa: E402

logger = get_logger("launch_meta_ad")

FOUNDER_USER_ID = os.getenv("FOUNDER_USER_ID", "founder")


def require_env(*names: str) -> None:
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        sys.exit(f"❌ Missing in .env: {', '.join(missing)}")


def get_platform(require_account: bool = True):
    require_env("META_ACCESS_TOKEN", *(["META_AD_ACCOUNT_ID"] if require_account else []))
    return AdsFactory.get_platform(
        "meta",
        access_token=os.getenv("META_ACCESS_TOKEN"),
        account_id=os.getenv("META_AD_ACCOUNT_ID", ""),
        page_id=os.getenv("META_PAGE_ID"),
    )


def cmd_check() -> None:
    """Dry checks — also discovers ad account / page ids when not yet in .env."""
    platform = get_platform(require_account=False)
    who = platform.whoami()
    print(f"✅ Token OK — user: {who['user'].get('name')} ({who['user'].get('id')})")
    print("   Accessible ad accounts (META_AD_ACCOUNT_ID candidates):")
    for acct in who["ad_accounts"]:
        print(f"     - {acct.get('id')}  {acct.get('name')}  [{acct.get('currency')}]")

    if os.getenv("META_AD_ACCOUNT_ID"):
        info = platform.get_account_info()
        print(f"✅ Target ad account: {info.get('id')} ({info.get('name')}, {info.get('currency')})")
    else:
        print("⚠️  META_AD_ACCOUNT_ID not set — pick one from the list above")

    if os.getenv("META_PAGE_ID"):
        page = platform.check_page()
        print(f"✅ Page OK: {page.get('name')} ({page.get('id')})")
    else:
        pages = platform.list_pages()
        if pages:
            print("⚠️  META_PAGE_ID not set — pages you manage (candidates):")
            for p in pages:
                print(f"     - {p.get('id')}  {p.get('name')}")
        else:
            print("⚠️  META_PAGE_ID not set and no pages visible to this token "
                  "(token needs pages_show_list, or create a FB Page first)")


def cmd_activate(launch_id: str) -> None:
    launch = ads_db.get_ad_launch(launch_id)
    if not launch:
        sys.exit(f"❌ No launch {launch_id}")
    if launch["status"] not in ("paused", "active"):
        sys.exit(f"❌ Launch is '{launch['status']}' — only paused launches can be activated")

    budget = launch["config"]["daily_budget_cents"]
    print(f"About to ACTIVATE: {launch.get('name')} — daily budget {budget} (minor units), "
          f"landing {launch['config']['landing_url']}")
    print("This will start REAL SPEND once Meta approves the ad.")
    if input("Type ACTIVATE to confirm: ").strip() != "ACTIVATE":
        sys.exit("Aborted.")

    platform = get_platform()
    platform.set_status(launch["platform_ids"], "ACTIVE")
    ads_db.update_ad_launch(launch_id, {"status": "active"})
    print(f"✅ Activated. Pause anytime with: --pause --launch-id {launch_id}")


def cmd_pause(launch_id: str) -> None:
    launch = ads_db.get_ad_launch(launch_id)
    if not launch:
        sys.exit(f"❌ No launch {launch_id}")
    platform = get_platform()
    platform.set_status(launch["platform_ids"], "PAUSED")
    ads_db.update_ad_launch(launch_id, {"status": "paused"})
    print("✅ Paused.")


def run_launch(launch_id: str) -> None:
    """Execute (or resume) the launch state machine for an existing doc."""
    launch = ads_db.get_ad_launch(launch_id)
    if not launch:
        sys.exit(f"❌ No launch {launch_id}")

    spec = LaunchSpec(
        launch_id=launch_id,
        name=launch["name"],
        video_url=launch["video_url"],
        thumbnail_url=launch.get("thumbnail_url"),
        page_id=os.getenv("META_PAGE_ID"),
        ad_copies=[AdCopy(**v) for v in get_copy_variants(launch)],
        config=LaunchConfig(**launch["config"]),
    )

    platform = get_platform()
    ads_db.update_ad_launch(launch_id, {"status": "launching", "error": None})
    try:
        ids = platform.launch(
            spec,
            platform_ids=launch.get("platform_ids", {}),
            persist=lambda key, value: ads_db.set_platform_id(launch_id, key, value),
        )
        # Legacy aliases = variant 0 (readers from before A/B variants)
        for legacy, indexed in (("creative_id", "creative_id_0"), ("ad_id", "ad_id_0")):
            if ids.get(indexed) and not ids.get(legacy):
                ads_db.set_platform_id(launch_id, legacy, ids[indexed])
    except Exception as e:
        ads_db.update_ad_launch(launch_id, {"status": "error", "error": str(e)})
        print(f"\n❌ Launch failed at a step: {e}")
        print(f"   Fix the cause and resume with: --resume --launch-id {launch_id}")
        raise SystemExit(1)

    import time as _time
    ads_db.update_ad_launch(launch_id, {"status": "paused", "launched_at": _time.time()})

    account_num = os.getenv("META_AD_ACCOUNT_ID", "").replace("act_", "")
    print("\n✅ Launch complete — everything is PAUSED.")
    print(f"   launch_id:   {launch_id}")
    for key, value in ids.items():
        print(f"   {key:13} {value}")
    print(f"\n   Ads Manager: https://adsmanager.facebook.com/adsmanager/manage/campaigns"
          f"?act={account_num}&selected_campaign_ids={ids.get('campaign_id')}")
    print(f"   Activate:    python scripts/ads/launch_meta_ad.py --activate --launch-id {launch_id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = parser.add_argument_group("creative source (one required for new launches)")
    src.add_argument("--run-id", help="IgniteAI execution run id (reads result.video_url)")
    src.add_argument("--video-url", help="Any publicly fetchable video URL")

    cfg = parser.add_argument_group("campaign config")
    cfg.add_argument("--daily-budget-cents", type=int, help="Daily budget in minor currency units")
    cfg.add_argument("--landing-url", help="Click-through destination URL")
    cfg.add_argument("--objective", default="OUTCOME_TRAFFIC", choices=["OUTCOME_TRAFFIC", "OUTCOME_SALES"])
    cfg.add_argument("--cta", default="LEARN_MORE", help="Meta CTA type (LEARN_MORE, SHOP_NOW, SIGN_UP, ...)")
    cfg.add_argument("--countries", default="IN", help="Comma-separated ISO country codes")
    cfg.add_argument("--age-min", type=int, default=18)
    cfg.add_argument("--age-max", type=int, default=65)
    cfg.add_argument("--name", help="Campaign name (default: derived from launch id)")

    copy = parser.add_argument_group("ad copy (manual or --ai-copy)")
    copy.add_argument("--ai-copy", action="store_true", help="Generate copy with Gemini from run script + brand kit")
    copy.add_argument("--num-variants", type=int, default=1, choices=[1, 2, 3],
                      help="A/B test: ads per launch, one per Gemini copy variant (needs --ai-copy)")
    copy.add_argument("--primary-text")
    copy.add_argument("--headline")
    copy.add_argument("--description", default="")

    ops = parser.add_argument_group("operations")
    ops.add_argument("--check", action="store_true", help="Dry checks only (token/account/page)")
    ops.add_argument("--resume", action="store_true", help="Resume an interrupted launch")
    ops.add_argument("--activate", action="store_true", help="Activate a paused launch (typed confirm)")
    ops.add_argument("--pause", action="store_true", help="Pause an active launch")
    ops.add_argument("--launch-id", help="Existing launch id (for --resume/--activate/--pause)")
    ops.add_argument("--user-id", default=FOUNDER_USER_ID, help="Owner user id (default: founder)")

    args = parser.parse_args()

    if args.check:
        return cmd_check()
    if args.activate:
        if not args.launch_id:
            sys.exit("--activate requires --launch-id")
        return cmd_activate(args.launch_id)
    if args.pause:
        if not args.launch_id:
            sys.exit("--pause requires --launch-id")
        return cmd_pause(args.launch_id)
    if args.resume:
        if not args.launch_id:
            sys.exit("--resume requires --launch-id")
        return run_launch(args.launch_id)

    # ----- new launch -----
    if not args.daily_budget_cents or not args.landing_url:
        sys.exit("New launches require --daily-budget-cents and --landing-url")
    if not args.run_id and not args.video_url:
        sys.exit("Provide a creative source: --run-id or --video-url")
    require_env("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID", "META_PAGE_ID")

    max_budget = int(os.getenv("ADS_MAX_DAILY_BUDGET_CENTS", "50000"))
    if args.daily_budget_cents > max_budget:
        sys.exit(f"❌ Budget {args.daily_budget_cents} exceeds cap ADS_MAX_DAILY_BUDGET_CENTS={max_budget}")

    # Resolve creative source
    video_url = args.video_url
    video_script = ""
    if args.run_id:
        run = ads_db.get_execution(args.run_id)
        if not run:
            sys.exit(f"❌ No execution {args.run_id}")
        video_url = (run.get("result") or {}).get("video_url")
        if not video_url:
            sys.exit(f"❌ Run {args.run_id} has no final video URL (status: {run.get('status')})")
        video_script = str((run.get("result") or {}).get("config", {}).get("prompt", ""))

    # Resolve copy (1-3 variants → one ad each inside the shared adset)
    if args.num_variants > 1 and not args.ai_copy:
        sys.exit("--num-variants > 1 needs --ai-copy (manual copy is single-variant)")
    if args.ai_copy:
        from backend.services.ads_service.ai_copy import generate_ad_copy_variants
        brand = ads_db.get_brand(args.user_id)
        suggestions = generate_ad_copy_variants(video_script, args.landing_url, brand,
                                                num_variants=args.num_variants)
        print(f"\nAI copy suggestion{'s' if len(suggestions) > 1 else ''}:")
        for i, s in enumerate(suggestions):
            if len(suggestions) > 1:
                print(f"  — variant {i + 1} —")
            for k, v in s.items():
                print(f"  {k}: {v}")
        if input("Use this copy? [Y/n]: ").strip().lower() in ("n", "no"):
            sys.exit("Aborted — re-run with manual --primary-text/--headline.")
        ad_copies = [AdCopy(**s, ai_generated=True) for s in suggestions]
    elif args.primary_text and args.headline:
        ad_copies = [AdCopy(primary_text=args.primary_text, headline=args.headline,
                            description=args.description)]
    else:
        sys.exit("Provide copy: --ai-copy OR both --primary-text and --headline")

    # Seed the founder ad_accounts doc (multi-tenant model from day one)
    account = ads_db.upsert_env_ad_account(
        args.user_id, "meta",
        account_id=os.getenv("META_AD_ACCOUNT_ID"),
        page_id=os.getenv("META_PAGE_ID"),
    )

    launch_id = new_launch_id()
    name = args.name or f"IgniteAds {args.run_id or launch_id}"
    config = LaunchConfig(
        objective=args.objective,
        daily_budget_cents=args.daily_budget_cents,
        landing_url=args.landing_url,
        cta_type=args.cta,
        targeting=Targeting(countries=args.countries.split(","),
                            age_min=args.age_min, age_max=args.age_max),
    )

    credits = charge_ad_launch(args.user_id, launch_id,
                               {**config.model_dump(), "num_variants": len(ad_copies)})
    created = ads_db.create_ad_launch(launch_id, args.user_id, {
        "platform": "meta",
        "ad_account_doc_id": account["doc_id"],
        "source_run_id": args.run_id,
        "video_url": video_url,
        "name": name,
        "config": config.model_dump(),
        # `copy` stays = variant 0 for pre-variant readers
        "copy": ad_copies[0].model_dump(),
        "copy_variants": [c.model_dump() for c in ad_copies],
        "num_variants": len(ad_copies),
        "credits_charged": credits,
    })
    if not created:
        sys.exit(f"❌ Launch {launch_id} already exists (should never happen with fresh UUIDs)")

    print(f"\n🚀 Launching '{name}' → PAUSED campaign on {account['account_id']}")
    run_launch(launch_id)


if __name__ == "__main__":
    main()
