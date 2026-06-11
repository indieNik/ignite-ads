#!/usr/bin/env python3
"""
Records a scripted product demo of https://ads.igniteai.in with Playwright.

Single continuous take; every narrative beat's timestamp (relative to video
start) is logged to scenes.json so cut_and_narrate.py can trim dead time,
lay voiceover, and burn captions.

Auth: mints a Firebase custom token for the founder UID and signs in via the
CDN Firebase SDK inside the page — the bundled app picks the session up from
IndexedDB on reload (same apiKey + [DEFAULT] app name → same persistence key).
"""
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(ROOT, ".env"))

from playwright.sync_api import sync_playwright  # noqa: E402

from backend.firebase_setup import initialize_firebase  # noqa: E402

APP_URL = "https://ads.igniteai.in"
OUT_DIR = os.path.join(ROOT, ".tmp", "demo")
FOUNDER_UID = os.getenv("FOUNDER_USER_ID")

FIREBASE_CONFIG = {
    "apiKey": "AIzaSyDmvzFcgDYAN-4GzZBNVsYINYymGhw_4qc",
    "authDomain": "ignite-ai-01.firebaseapp.com",
    "projectId": "ignite-ai-01",
}

FAKE_CURSOR = """
const dot = document.createElement('div');
dot.style.cssText = 'position:fixed;width:18px;height:18px;border-radius:50%;' +
  'background:rgba(157,134,255,.85);border:2px solid #fff;z-index:99999;' +
  'pointer-events:none;transform:translate(-50%,-50%);transition:left .05s,top .05s;' +
  'box-shadow:0 0 12px rgba(109,74,255,.8)';
document.addEventListener('DOMContentLoaded', () => document.body.appendChild(dot));
window.addEventListener('mousemove', e => { dot.style.left = e.clientX+'px'; dot.style.top = e.clientY+'px'; });
"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    initialize_firebase()
    from firebase_admin import auth as fb_auth
    custom_token = fb_auth.create_custom_token(FOUNDER_UID).decode()

    scenes = []
    t0 = [None]

    def mark(name):
        t = time.monotonic() - t0[0]
        scenes.append({"name": name, "t": round(t, 2)})
        print(f"  [{t:7.2f}s] {name}", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=OUT_DIR,
            record_video_size={"width": 1440, "height": 900},
        )
        ctx.add_init_script(FAKE_CURSOR)
        page = ctx.new_page()
        t0[0] = time.monotonic()

        # ---- Scene: hero / sign-in
        page.goto(APP_URL, wait_until="networkidle")
        mark("hero_start")
        page.mouse.move(720, 430)
        page.wait_for_timeout(5000)
        mark("hero_end")

        # ---- Auth via custom token (off-camera beat, will be cut)
        page.evaluate("""async (cfg) => {
            const appMod = await import('https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js');
            const authMod = await import('https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js');
            const app = appMod.initializeApp(cfg.config);
            await authMod.signInWithCustomToken(authMod.getAuth(app), cfg.token);
            await new Promise(r => setTimeout(r, 1500));
        }""", {"config": FIREBASE_CONFIG, "token": custom_token})
        page.reload(wait_until="networkidle")
        page.wait_for_selector("text=Campaigns", timeout=30000)
        page.wait_for_timeout(1500)
        mark("dash_start")
        page.mouse.move(700, 250)
        page.wait_for_timeout(2500)
        page.mouse.move(700, 470)
        page.wait_for_timeout(3000)
        mark("dash_end")

        # ---- Scene: launch modal + Gemini copy
        page.click("text=+ Launch an ad")
        page.wait_for_selector("text=New launch")
        mark("modal_start")
        page.wait_for_timeout(1500)
        # pick the first available completed run
        page.select_option("select", index=1)
        page.wait_for_timeout(1500)
        mark("gemini_click")
        page.click("text=Suggest with Gemini")
        # wait for typewriter to finish: headline filled AND button re-enabled
        page.wait_for_function(
            """() => {
                const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('Suggest'));
                const inputs = document.querySelectorAll('.modal input');
                return btn && !btn.disabled && inputs[1] && inputs[1].value.length > 3;
            }""", timeout=90000)
        page.wait_for_timeout(2000)
        mark("gemini_done")
        page.wait_for_timeout(2000)

        # ---- Scene: launch (PAUSED)
        launch_id = [None]
        def on_response(resp):
            if resp.url.endswith("/api/ads/launch") and resp.status == 200:
                try:
                    launch_id[0] = resp.json().get("launch_id")
                except Exception:
                    pass
        page.on("response", on_response)
        mark("launch_click")
        page.click("text=Launch (PAUSED)")
        page.wait_for_selector("text=Launching:", timeout=30000)
        page.wait_for_timeout(6000)
        mark("busy_end")

        # ---- off-camera: wait for the launch to finish (cut from video)
        print(f"  waiting for launch {launch_id[0]} to complete…", flush=True)
        deadline = time.time() + 420
        while time.time() < deadline:
            page.wait_for_timeout(5000)
            statuses = page.eval_on_selector_all(".badge", "els => els.map(e => e.textContent.trim())")
            if statuses and "launching" not in [s.lower() for s in statuses]:
                break

        # ---- Scene: final dashboard with the new campaign
        page.reload(wait_until="networkidle")
        page.wait_for_selector("text=Campaigns")
        page.wait_for_timeout(1500)
        mark("final_start")
        page.mouse.move(700, 240)
        page.wait_for_timeout(2500)
        # hover the new campaign's Activate button
        btn = page.query_selector("text=Activate")
        if btn:
            btn.hover()
        page.wait_for_timeout(3500)
        page.mouse.move(860, 330)
        page.wait_for_timeout(3000)
        mark("final_end")

        video_path = page.video.path()
        ctx.close()
        browser.close()

    final_video = os.path.join(OUT_DIR, "raw_take.webm")
    os.replace(video_path, final_video)
    with open(os.path.join(OUT_DIR, "scenes.json"), "w") as f:
        json.dump({"video": final_video, "scenes": scenes, "launch_id": launch_id[0]}, f, indent=2)
    print(f"\n✅ take saved: {final_video}")
    print(f"   scenes: {json.dumps(scenes)}")


if __name__ == "__main__":
    main()
