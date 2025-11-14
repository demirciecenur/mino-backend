#!/usr/bin/env python3
import os
import sys
import json
import argparse
from dotenv import load_dotenv

# Allow running from repo root or backend dir
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Load .env file from backend directory
env_path = os.path.join(BACKEND_DIR, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    # Try parent directory (repo root)
    parent_env = os.path.join(os.path.dirname(BACKEND_DIR), ".env")
    if os.path.exists(parent_env):
        load_dotenv(parent_env)

from services.story_composer import (
    generate_story_with_openai,
    to_character_slug,
    content_story_path,
)


def main():
    parser = argparse.ArgumentParser(description="Compose a per-character/topic story via OpenAI and save JSON.")
    parser.add_argument("--character", required=True, help="Display character name (e.g., Luna)")
    parser.add_argument("--topic", required=True, help="Topic id (e.g., behavior_attention)")
    parser.add_argument("--lang", required=True, help="Language code (e.g., tr or en)")
    parser.add_argument("--minutes", type=int, default=10, help="Target duration in minutes (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Print JSON to stdout without saving")
    args = parser.parse_args()

    print(f"🔮 Composing story via OpenAI... character={args.character} topic={args.topic} lang={args.lang} minutes={args.minutes}")
    data = asyncio_run(generate_story_with_openai(
        character=args.character,
        topic=args.topic,
        lang=args.lang,
        duration_minutes=args.minutes,
    ))

    if args.dry_run:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    slug = to_character_slug(args.character)
    out_path = content_story_path(args.lang, slug, args.topic)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ Saved: {out_path}")
    return 0


def asyncio_run(coro):
    try:
        import asyncio
        return asyncio.run(coro)
    except RuntimeError:
        # In case we're inside an event loop
        import nest_asyncio
        nest_asyncio.apply()
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)


if __name__ == "__main__":
    sys.exit(main())
