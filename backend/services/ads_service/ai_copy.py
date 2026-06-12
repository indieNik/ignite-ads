"""
AI ad copy — derives Meta ad copy (primary text / headline / description)
from the source video's script and the user's brand kit.

Uses Gemini via google-genai with JSON output. Copy is always a *suggestion*:
the CLI (Phase A) prints it for review and the launch wizard (Phase B) makes
it editable before launch. One call can return up to MAX_COPY_VARIANTS
distinct variants — the unit of an A/B test (one ad per variant).
"""
import json
import os
from typing import Any, Dict, List, Optional

from backend.logger import get_logger
from backend.services.ads_service.base import MAX_COPY_VARIANTS

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

You will be asked for a specific number of variants. Each variant must take a
clearly different angle — e.g. curiosity hook vs. direct benefit vs. social
proof/urgency. Different primary_text AND headline, never paraphrases of each other.

Return STRICT JSON:
{"variants": [{"primary_text": str, "headline": str, "description": str}, ...]}
with EXACTLY the number of variants requested."""


def generate_ad_copy_variants(
    video_script: str,
    landing_url: str,
    brand: Optional[Dict[str, Any]] = None,
    product_hint: str = "",
    num_variants: int = 1,
) -> List[Dict[str, str]]:
    """Returns num_variants dicts of {primary_text, headline, description}.
    Raises on LLM failure — callers fall back to manual copy."""
    from google import genai

    if not 1 <= num_variants <= MAX_COPY_VARIANTS:
        raise ValueError(f"num_variants must be 1-{MAX_COPY_VARIANTS}, got {num_variants}")

    brand_block = ""
    if brand:
        brand_block = (f"\nBrand: {brand.get('name', '')}"
                       f"\nBrand voice/character: {brand.get('character_prompt', '')}")

    user_prompt = (
        f"Video script / narration:\n{video_script or '(unavailable — write from the product hint)'}\n"
        f"{brand_block}\n"
        f"Product hint: {product_hint or '(none)'}\n"
        f"Landing page: {landing_url}\n\n"
        f"Write exactly {num_variants} ad copy variant(s) now."
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
    variants = data.get("variants")
    if not isinstance(variants, list) or len(variants) != num_variants:
        raise ValueError(f"AI copy returned {len(variants) if isinstance(variants, list) else 'no'} "
                         f"variants, expected {num_variants}: {data}")
    for v in variants:
        for key in ("primary_text", "headline", "description"):
            if key not in v:
                raise ValueError(f"AI copy variant missing '{key}': {v}")
    logger.info("AI ad copy generated",
                extra={"data": {"headlines": [v["headline"] for v in variants]}})
    return [{k: v[k] for k in ("primary_text", "headline", "description")} for v in variants]


def generate_ad_copy(
    video_script: str,
    landing_url: str,
    brand: Optional[Dict[str, Any]] = None,
    product_hint: str = "",
) -> Dict[str, str]:
    """Single-variant convenience wrapper (legacy callers)."""
    return generate_ad_copy_variants(video_script, landing_url, brand, product_hint, 1)[0]
