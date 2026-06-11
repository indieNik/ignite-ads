"""
AI ad copy — derives Meta ad copy (primary text / headline / description)
from the source video's script and the user's brand kit.

Uses Gemini via google-genai with JSON output. Copy is always a *suggestion*:
the CLI (Phase A) prints it for review and the launch wizard (Phase B) makes
it editable before launch.
"""
import json
import os
from typing import Any, Dict, Optional

from backend.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a direct-response media buyer writing Meta (Facebook/Instagram) ad copy
for a UGC-style video ad. Write copy that complements the video, never repeats it verbatim.

Hard rules (Meta ad policy):
- No personal attributes ("Are you struggling with YOUR acne?" is banned — never imply
  knowledge of the viewer's characteristics).
- No unrealistic claims, no before/after framing, no clickbait.
- Primary text: 1-3 short sentences, hook first, <=125 chars ideally. Emojis sparingly (max 2).
- Headline: <=40 chars, benefit-led.
- Description: <=30 chars, optional reinforcement.

Return STRICT JSON: {"primary_text": str, "headline": str, "description": str}"""


def generate_ad_copy(
    video_script: str,
    landing_url: str,
    brand: Optional[Dict[str, Any]] = None,
    product_hint: str = "",
) -> Dict[str, str]:
    """Returns {primary_text, headline, description}. Raises on LLM failure —
    callers fall back to manual copy."""
    from google import genai

    brand_block = ""
    if brand:
        brand_block = (f"\nBrand: {brand.get('name', '')}"
                       f"\nBrand voice/character: {brand.get('character_prompt', '')}")

    user_prompt = (
        f"Video script / narration:\n{video_script or '(unavailable — write from the product hint)'}\n"
        f"{brand_block}\n"
        f"Product hint: {product_hint or '(none)'}\n"
        f"Landing page: {landing_url}\n\n"
        "Write the ad copy JSON now."
    )

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    response = client.models.generate_content(
        model=os.getenv("ADS_COPY_MODEL", "gemini-2.5-flash"),
        contents=user_prompt,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json",
            "temperature": 0.8,
        },
    )
    data = json.loads(response.text)
    for key in ("primary_text", "headline", "description"):
        if key not in data:
            raise ValueError(f"AI copy missing '{key}': {data}")
    logger.info("AI ad copy generated", extra={"data": {"headline": data["headline"]}})
    return {k: data[k] for k in ("primary_text", "headline", "description")}
