#!/usr/bin/env python3
"""
Exchange a short-lived Meta user token for a long-lived (~60 day) one.

The token generator in the Meta dev console (Marketing API → Tools → Get Token)
issues short-lived tokens (~1-2h). Run this once after grabbing one:

    python scripts/ads/exchange_token.py --token <SHORT_LIVED_TOKEN>

Requires META_APP_ID and META_APP_SECRET in .env. Prints the long-lived token
and its expiry — paste it into .env as META_ACCESS_TOKEN.
"""
import argparse
import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

GRAPH_VERSION = os.getenv("META_GRAPH_API_VERSION", "v23.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--token", required=True, help="Short-lived token from the Meta dev console")
    args = parser.parse_args()

    app_id = os.getenv("META_APP_ID")
    app_secret = os.getenv("META_APP_SECRET")
    if not app_id or not app_secret:
        sys.exit("META_APP_ID / META_APP_SECRET missing in .env (App settings → Basic in the dev console)")

    resp = requests.get(f"{GRAPH_BASE}/oauth/access_token", params={
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": args.token,
    }, timeout=30)
    body = resp.json()
    if "error" in body:
        sys.exit(f"Exchange failed: {body['error'].get('message')}")

    long_token = body["access_token"]

    # Inspect actual expiry via debug_token
    debug = requests.get(f"{GRAPH_BASE}/debug_token", params={
        "input_token": long_token,
        "access_token": f"{app_id}|{app_secret}",
    }, timeout=30).json().get("data", {})

    expires_at = debug.get("data_access_expires_at") or debug.get("expires_at")
    expiry_str = (datetime.fromtimestamp(expires_at, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                  if expires_at else "unknown (likely ~60 days)")

    print("\n✅ Long-lived token obtained")
    print(f"   Expires: {expiry_str}")
    print(f"   Scopes:  {', '.join(debug.get('scopes', [])) or 'unknown'}")
    print("\nAdd to .env:\n")
    print(f"META_ACCESS_TOKEN={long_token}\n")


if __name__ == "__main__":
    main()
