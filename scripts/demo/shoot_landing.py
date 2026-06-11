#!/usr/bin/env python3
"""Screenshot the live landing page (desktop full-page + mobile) for visual QA."""
import os
import sys

from playwright.sync_api import sync_playwright

OUT = os.path.join(os.path.dirname(__file__), "../../.tmp/demo")
URL = sys.argv[1] if len(sys.argv) > 1 else "https://ads.igniteai.in/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(2500)
    page.screenshot(path=f"{OUT}/landing_hero.png")
    # scroll through so GSAP reveals fire, then full-page shot
    page.evaluate("async () => { for (let y=0; y<=document.body.scrollHeight; y+=300) { scrollTo(0,y); await new Promise(r=>setTimeout(r,60)); } scrollTo(0,0); }")
    page.wait_for_timeout(1200)
    page.screenshot(path=f"{OUT}/landing_full.png", full_page=True)

    m = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    m.goto(URL, wait_until="networkidle")
    m.wait_for_timeout(2500)
    m.screenshot(path=f"{OUT}/landing_mobile_hero.png")
    m.evaluate("async () => { for (let y=0; y<=document.body.scrollHeight; y+=300) { scrollTo(0,y); await new Promise(r=>setTimeout(r,50)); } }")
    m.wait_for_timeout(800)
    m.screenshot(path=f"{OUT}/landing_mobile_full.png", full_page=True)

    # app still works at /app
    a = browser.new_page(viewport={"width": 1280, "height": 800})
    a.goto(URL.rstrip("/") + "/app", wait_until="networkidle")
    a.wait_for_timeout(2000)
    a.screenshot(path=f"{OUT}/app_at_subpath.png")
    browser.close()

print("shots saved to .tmp/demo/")
