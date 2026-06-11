#!/usr/bin/env python3
"""
Produce the final narrated demo from the raw Playwright take:
cut dead time → ElevenLabs voiceover per scene → pad scenes to fit VO →
concat → burn captions → mux. Output: .tmp/demo/igniteads-demo.mp4
"""
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(ROOT, ".env"))
# ElevenLabs key lives in the IgniteAI repo's .env
load_dotenv("/Users/publicissapient/Projects/AI-Projects/AI UGC Ad Video Builder/.env")

import requests  # noqa: E402

DEMO = os.path.join(ROOT, ".tmp", "demo")
RAW = os.path.join(DEMO, "raw_take.webm")
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel (free tier)

# (start, end, narration) — cut windows in raw-take seconds
SEGMENTS = [
    (0.9, 6.7, "This is IgniteAds — where your AI-generated videos become real, running ads."),
    (19.5, 25.1, "Sign in, and every campaign is right here — status, budget, and Meta's review state at a glance."),
    (25.2, 32.2, "Pick any video you've generated… and Gemini writes policy-safe ad copy in seconds."),
    (32.2, 40.2, "One click builds the entire Meta campaign — video, creative, ad set and ad — all completely paused. No spend until you say go."),
    (121.0, 130.0, "Minutes later, it's live in your Ads Manager, ready to activate. Generate. Launch. Measure. IgniteAds — at ads dot igniteai dot in."),
]


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def tts(text, out_path):
    """ElevenLabs first; Gemini TTS fallback (ElevenLabs free quota 402s)."""
    try:
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
            headers={"xi-api-key": os.getenv("ELEVENLABS_API_KEY", ""), "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
            timeout=120,
        )
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(resp.content)
        return
    except Exception as e:
        print(f"  elevenlabs unavailable ({e}); using Gemini TTS", flush=True)

    import wave
    from google import genai
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    resp = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=f"Say in an upbeat, confident product-demo narrator voice: {text}",
        config={
            "response_modalities": ["AUDIO"],
            "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": "Kore"}}},
        },
    )
    pcm = resp.candidates[0].content.parts[0].inline_data.data
    wav_path = out_path.replace(".mp3", ".wav")
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path, "-b:a", "192k", out_path])


def fmt_ts(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s % 1) * 1000):03}"


def main():
    seg_files, srt_lines, cursor = [], [], 0.0
    for i, (a, b, text) in enumerate(SEGMENTS):
        vid = os.path.join(DEMO, f"seg{i}.mp4")
        vo = os.path.join(DEMO, f"seg{i}.mp3")
        av = os.path.join(DEMO, f"seg{i}_av.mp4")

        print(f"segment {i}: cut {a}–{b}, tts {len(text)} chars", flush=True)
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(a), "-to", str(b), "-i", RAW,
             "-an", "-r", "30", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
             "-pix_fmt", "yuv420p", vid])
        tts(text, vo)

        vdur, adur = duration(vid), duration(vo)
        target = round(max(vdur, adur + 0.5), 2)
        # freeze last frame if VO outruns the footage; pad audio tail to target
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", vid, "-i", vo,
             "-filter_complex",
             f"[0:v]tpad=stop_mode=clone:stop_duration={max(0, target - vdur):.2f}[v];"
             f"[1:a]apad=whole_dur={target}[a]",
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", str(target), av])

        srt_lines.append((len(srt_lines) + 1, cursor + 0.05, cursor + adur + 0.35, text.replace("…", "...")))
        cursor += target
        seg_files.append(av)

    concat_list = os.path.join(DEMO, "concat.txt")
    with open(concat_list, "w") as f:
        f.writelines(f"file '{p}'\n" for p in seg_files)
    merged = os.path.join(DEMO, "merged.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", concat_list, "-c", "copy", merged])

    srt = os.path.join(DEMO, "captions.srt")
    with open(srt, "w") as f:
        for n, a, b, text in srt_lines:
            f.write(f"{n}\n{fmt_ts(a)} --> {fmt_ts(b)}\n{text}\n\n")

    final = os.path.join(DEMO, "igniteads-demo.mp4")
    style = ("FontName=Helvetica,FontSize=13,PrimaryColour=&H00FFFFFF,OutlineColour=&H88000000,"
             "BorderStyle=1,Outline=1,Shadow=1,MarginV=28")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", merged,
         "-vf", f"subtitles={srt}:force_style='{style}'",
         "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "copy", final])

    print(f"\n✅ {final}  ({duration(final):.1f}s)")


if __name__ == "__main__":
    main()
