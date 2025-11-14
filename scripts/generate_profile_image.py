#!/usr/bin/env python3
"""
Generate a child-friendly square profile image for a character from two reference photos.

Features:
- Creates iOS asset folder: mino/mino/Assets/characters/{slug}/
- Calls FAL.ai image-to-image model (InstantID or IP-Adapter) if FAL_API_KEY is set
- Falls back to a simple blended placeholder if no API key (for quick iteration)

Usage:
  python backend/scripts/generate_profile_image.py \
    --character "Tiko" \
    --ref1 /path/to/ref1.jpg \
    --ref2 /path/to/ref2.jpg \
    --model instantid \
    --out-size 1024

Environment:
  FAL_API_KEY=<your_fal_api_key>

Outputs:
  mino/mino/Assets/characters/{slug}/{slug}_profile.png
"""
import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[2]
IOS_ASSETS_ROOT = PROJECT_ROOT / "mino" / "mino" / "Assets" / "characters"


DERIVATIVE_ALIASES = {
    # Safe ASO derivative → ORIGIN canonical slug (folders named by origin)
    "spider fighter": "spiderman",
    "elisa the ice fairy": "elsa",
    "yellow buddy": "minion",
    "chirpy birdie": "tweety",
    "bubble buddy": "spongebob",
    "funny bunny": "bugsbunny",
    "super metal hero": "ironman",
    "piggy friend": "peppapig",
    "blu pup": "bluey",
    "rescue pup crew": "pawpatrol",
    "ocean dreamer moa": "moana",
    "super jump hero": "mario",
    "swamp buddy hero": "shrek",
    "boots knight pal": "pussinboots",
    "frost friend sid": "sid",
    "adventure dora pal": "dora",
    "snowman buddy olaf-style": "olaf",
    "spark buddy": "pikachu",
    "mystery pup buddy": "scoobydoo",
    "sneaky cat tom": "tom",
    "clever mouse jerry": "jerry",
    "shell heroes crew": "ninjaturtles",
}

ORIGINALS = {
    "mino": "mino",
    "luna": "luna",
    "tiko": "tiko",
    "bubu": "bubu",
    "sunny": "sunny",
    "koko": "koko",
    "winnie": "winnie",
}


def slugify_character(name: str) -> str:
    n = name.strip().lower()
    if n in DERIVATIVE_ALIASES:
        return DERIVATIVE_ALIASES[n]
    if n in ORIGINALS:
        return ORIGINALS[n]
    # generic slug: letters and digits, hyphens for others
    return "".join(ch if ch.isalnum() else "-" for ch in n).strip("-")


def ensure_asset_folder(slug: str) -> Path:
    out_dir = IOS_ASSETS_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def load_image_square(path: Path, size: int) -> Image.Image:
    img = Image.open(path).convert("RGB")
    img = ImageOps.exif_transpose(img)
    img = ImageOps.fit(img, (size, size), Image.BICUBIC, bleed=0.0, centering=(0.5, 0.5))
    return img


def blended_placeholder(ref1: Path, ref2: Path, size: int) -> Image.Image:
    a = load_image_square(ref1, size)
    b = load_image_square(ref2, size)
    # simple average blend then add soft vignette for profile feel
    avg = Image.blend(a, b, alpha=0.5)
    # light pastel overlay
    overlay = Image.new("RGB", (size, size), (240, 246, 255))
    final = Image.blend(avg, overlay, alpha=0.15)
    return final


def build_character_prompt(name: str) -> str:
    n = name.strip()
    # Base, child-safe profile constraints
    base = (
        f"{n} inspired kid-friendly character profile, close-up headshot, smiling, gentle eye contact, "
        "soft pastel flat background, centered composition, clean edges, high detail yet simple, "
        "round-friendly shapes, wholesome, kind expression, studio lighting, portrait photo style"
    )

    # Per-character tone/voice/age and visual flavor (ASO-safe, no brands/logos)
    meta = {
        "Spider Fighter": {"tone": "adventure, courage", "voice": "excited, energetic", "age": "boy 4-7", "flavor": "subtle city-hero vibe (no logos)"},
        "Elisa the Ice Fairy": {"tone": "imagination, grace", "voice": "gentle, calm", "age": "girl 4-7", "flavor": "icy sparkle bokeh, soft snow-glow rim light (no logos)"},
        "Yellow Buddy": {"tone": "comedy, friendship", "voice": "fun, cheerful", "age": "mixed 3-6", "flavor": "banana-yellow accents, playful"},
        "Chirpy Birdie": {"tone": "sweet, caring", "voice": "high, cheerful", "age": "mixed 3-5", "flavor": "sunny cheerful tone, tiny feather hint"},
        "Bubble Buddy": {"tone": "humor, fun", "voice": "lively, enthusiastic", "age": "boy 4-7", "flavor": "underwater blue-green palette, soft bubble bokeh"},
        "Funny Bunny": {"tone": "witty, classic", "voice": "clever, playful", "age": "mixed 4-7", "flavor": "tiny carrot color hint"},
        "Super Metal Hero": {"tone": "strength, protection", "voice": "confident", "age": "boy 5-8", "flavor": "sleek metallic accents (no logos)"},
        "Piggy Friend": {"tone": "sweet, simple", "voice": "soft, kind", "age": "girl 2-4", "flavor": "warm farm-day feel"},
        "Blu Pup": {"tone": "joy, family", "voice": "cheerful, caring", "age": "mixed 3-6", "flavor": "sky-blue accent"},
        "Rescue Pup Crew": {"tone": "teamwork, helping", "voice": "brave, friendly", "age": "mixed 2-6", "flavor": "bright helper accents"},
        "Ocean Dreamer Moa": {"tone": "explore, courage", "voice": "adventurous, inspiring", "age": "mixed 4-8", "flavor": "ocean teal palette"},
        "Super Jump Hero": {"tone": "adventure, play", "voice": "energetic, happy", "age": "boy 4-8", "flavor": "game-like joy (no logos)"},
        "Swamp Buddy Hero": {"tone": "humor, acceptance", "voice": "witty, kind", "age": "mixed 4-8", "flavor": "green swampy warmth"},
        "Boots Knight Pal": {"tone": "adventure, courage", "voice": "confident, heroic", "age": "mixed 4-8", "flavor": "warm gold knight hint (no logos)"},
        "Frost Friend Sid": {"tone": "comedy, friendship", "voice": "funny, curious", "age": "mixed 3-7", "flavor": "frosty light blue-white accents"},
        "Adventure Dora Pal": {"tone": "explore, learning", "voice": "curious, energetic", "age": "mixed 3-6", "flavor": "warm earthy explorer"},
        "Snowman Buddy Olaf-style": {"tone": "fun, kindness", "voice": "cheerful, pure", "age": "mixed 3-7", "flavor": "snowy brightness, cozy warmth"},
        "Sneaky Cat Tom": {"tone": "comedy, chase", "voice": "fast, witty", "age": "mixed 4-7", "flavor": "subtle cat vibe"},
        "Clever Mouse Jerry": {"tone": "smart, witty", "voice": "light, energetic", "age": "mixed 4-7", "flavor": "tiny clever charm"},
        "Shell Heroes Crew": {"tone": "adventure, friendship", "voice": "brave, team spirit", "age": "boy 5-8", "flavor": "green hero hint (no logos)"},
        "Spark Buddy": {"tone": "loving, adventure", "voice": "cheerful, energetic", "age": "mixed 4-8", "flavor": "electric fun spark bokeh (abstract, safe)"},
        "Mystery Pup Buddy": {"tone": "curious, friendship", "voice": "fearless, curious", "age": "mixed 4-7", "flavor": "soft detective warmth"},
        "Mino": {"tone": "friendly, colorful", "voice": "warm, playful", "age": "mixed 4-8", "flavor": "colorful space friend"},
        "Luna": {"tone": "dreamy, calm", "voice": "gentle", "age": "mixed 4-8", "flavor": "night explorer glow"},
        "Tiko": {"tone": "energetic, kind", "voice": "bright, playful", "age": "mixed 4-8", "flavor": "green buddy accent"},
        "Bubu": {"tone": "cheerful, warm", "voice": "friendly", "age": "mixed 4-8", "flavor": "orange pal accent"},
        "Sunny": {"tone": "bright, happy", "voice": "optimistic", "age": "mixed 4-8", "flavor": "yellow sunny accent"},
        "Koko": {"tone": "creative, caring", "voice": "soft, encouraging", "age": "mixed 4-8", "flavor": "pink artist hint"},
    }
    m = meta.get(n)
    if m:
        base += f", tone: {m['tone']}, voice: {m['voice']}, target: {m['age']}, {m['flavor']}"

    # Future animation hint: keep features stable for later MP4 generation
    base += ", consistent facial features for animation, stable identity, clean silhouette"
    return base


def call_fal_instantid(prompt: str, negative: str, ref1_b64: str, ref2_b64: str, size: int) -> Optional[bytes]:
    api_key = os.getenv("FAL_API_KEY")
    if not api_key:
        return None
    url = "https://fal.run/fal-ai/instant-id"
    headers = {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "negative_prompt": negative,
        "image_size": size,
        # Some FAL models accept multiple refs as a list; InstantID commonly a single ref.
        # We pass the first as primary and the second as extra if supported.
        "input_images": [
            {"image_base64": ref1_b64},
            {"image_base64": ref2_b64},
        ],
        "guidance_scale": 6.0,
        "num_inference_steps": 28,
        "seed": 42,
    }
    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
    resp.raise_for_status()
    data = resp.json()
    # Expected: { "images": [{"content": "base64..."}] } or similar
    # Try common fields:
    if isinstance(data, dict):
        if "images" in data and data["images"]:
            item = data["images"][0]
            content_b64 = item.get("content") or item.get("image_base64")
            if content_b64:
                return base64.b64decode(content_b64)
        if "image" in data and isinstance(data["image"], str):
            return base64.b64decode(data["image"])
    raise RuntimeError("Unexpected FAL response format")


def image_file_to_b64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def main():
    parser = argparse.ArgumentParser(description="Generate character profile image from two references")
    parser.add_argument("--character", required=True, help="Character name, e.g., 'Tiko'")
    parser.add_argument("--ref1", required=True, help="Path to reference image 1")
    parser.add_argument("--ref2", required=True, help="Path to reference image 2")
    parser.add_argument("--model", default="instantid", choices=["instantid"], help="Model to use")
    parser.add_argument("--out-size", type=int, default=1024, help="Output square size")
    parser.add_argument("--prompt", default=None, help="Override prompt. If omitted, character-aware prompt is used.")
    parser.add_argument(
        "--negative",
        default="mature, scary, gore, logo, trademark, watermark, text, nsfw, harsh shadows, extra fingers, deformed, glitch, artifacts",
    )
    args = parser.parse_args()

    slug = slugify_character(args.character)
    out_dir = ensure_asset_folder(slug)
    out_path = out_dir / f"{slug}_profile.png"

    ref1 = Path(args.ref1)
    ref2 = Path(args.ref2)
    if not ref1.exists() or not ref2.exists():
        print("❌ Reference image not found", file=sys.stderr)
        sys.exit(1)

    api_key = os.getenv("FAL_API_KEY")
    if api_key:
        try:
            print("🌐 Using FAL.ai to synthesize profile image…")
            img1_b64 = image_file_to_b64(ref1)
            img2_b64 = image_file_to_b64(ref2)
            final_prompt = args.prompt or build_character_prompt(args.character)
            png_bytes = call_fal_instantid(final_prompt, args.negative, img1_b64, img2_b64, args.out_size)
            if png_bytes is None:
                raise RuntimeError("FAL returned no image, falling back")
            with open(out_path, "wb") as f:
                f.write(png_bytes)
            print(f"✅ Saved generated profile: {out_path}")
            return
        except Exception as e:
            print(f"⚠️ FAL generation failed: {e}. Falling back to blended placeholder.")

    # Fallback: blended placeholder
    print("🖼️ Creating blended placeholder profile (no FAL_API_KEY)")
    img = blended_placeholder(ref1, ref2, args.out_size)
    img.save(out_path, format="PNG")
    print(f"✅ Saved placeholder profile: {out_path}")


if __name__ == "__main__":
    main()


