#!/usr/bin/env python3
"""
Generate TTS audio files for visible characters from story JSON files.

This script:
1. Reads story JSON files from Content/{lang}/stories/{character}/{topic}.json
2. Extracts text from each scene
3. Generates TTS audio using character-specific voice settings
4. Saves audio files to backend/storage/characters/{character}/{lang}/{topic}_{scene_index}.wav

Usage:
    python backend/scripts/generate_character_audios_from_stories.py [--character CHARACTER] [--lang LANG] [--topic TOPIC] [--skip-existing]
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import Settings
from main import generate_tts_with_elevenlabs
from utils.text_cleaner import clean_text_for_tts

# 14 Visible Characters (from Remote Config)
VISIBLE_CHARACTERS = [
    ("Mino", "mino"),
    ("Luna", "luna"),
    ("Tiko", "tiko"),
    ("Bubu", "bubu"),
    ("Sunny", "sunny"),
    ("Koko", "koko"),
    ("Sneaky Cat Tom", "tom"),
    ("Clever Mouse Jerry", "jerry"),
    ("Elisa the Ice Fairy", "elsa"),
    ("Shell Heroes Crew", "ninjaturtles"),
    ("Spider Fighter", "spiderman"),
    ("Yellow Buddy", "minion"),
    ("Chirpy Birdie", "tweety"),
    ("Bubble Buddy", "spongebob"),
]

# Topics
TOPICS = [
    "bedtime",
    "behavior",
    "confidence",
    "emotional_regulation",
    "friendship",
    "imagination",
    "nutrition",
    "screen_time",
    "sibling",
    "transitions",
]

# Languages
LANGS = ["de", "en", "es", "fr", "tr"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Try both locations: backend/storage/content (primary) and mino/Content (fallback)
CONTENT_DIR_BACKEND = PROJECT_ROOT / "backend" / "storage" / "content"
CONTENT_DIR_IOS = PROJECT_ROOT / "mino" / "Content"


def get_story_path(lang: str, character_slug: str, topic: str) -> Path:
    """Get path to story JSON file. Try backend/storage/content first, then mino/Content."""
    # Primary: backend/storage/content/{lang}/stories/{character}/{topic}.json
    backend_path = CONTENT_DIR_BACKEND / lang / "stories" / character_slug / f"{topic}.json"
    if backend_path.exists():
        print(f"📖 Using backend path: {backend_path}")
        return backend_path
    
    # Fallback: mino/Content/{lang}/stories/{character}/{topic}.json
    ios_path = CONTENT_DIR_IOS / lang / "stories" / character_slug / f"{topic}.json"
    if ios_path.exists():
        print(f"📖 Using iOS path: {ios_path}")
        return ios_path
    
    # Debug: print both paths if neither exists
    print(f"⚠️ Story not found. Tried:")
    print(f"   Backend: {backend_path}")
    print(f"   iOS: {ios_path}")
    return backend_path  # Return backend path anyway for error message


def load_story(lang: str, character_slug: str, topic: str) -> Optional[dict]:
    """Load story JSON file."""
    story_path = get_story_path(lang, character_slug, topic)
    if not story_path.exists():
        return None
    
    try:
        with open(story_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading {story_path}: {e}")
        return None


def get_character_voice_settings(character_slug: str) -> dict:
    """Get character-specific voice settings from CHARACTER_VOICES."""
    settings = Settings()
    
    # Try exact match
    char_voice = settings.CHARACTER_VOICES.get(character_slug.lower())
    if char_voice:
        return char_voice
    
    # Try case-insensitive match
    for key, value in settings.CHARACTER_VOICES.items():
        if key.lower() == character_slug.lower():
            return value
    
    # Fallback to mino (should not happen for visible characters)
    print(f"⚠️  Voice settings not found for {character_slug}, using mino defaults")
    return settings.CHARACTER_VOICES.get("mino", {
        "voice": "child-friendly",
        "emotion": "calm",
        "speed": 0.85,
        "pitch": 0.95,
        "voice_id": "AZnzlk1XvdvUeBnXmlld",
        "storyteller": True,
    })


async def generate_audio_for_scene(
    character_slug: str,
    topic: str,
    scene_index: int,
    scene_text: str,
    lang: str,
    skip_existing: bool = False
) -> bool:
    """Generate TTS audio for a single scene."""
    settings = Settings()
    
    # Get character voice settings
    char_voice = get_character_voice_settings(character_slug)
    
    # Character directory with language subdirectory
    # Structure: backend/storage/characters/{character}/{lang}/{topic}_{scene_index}.wav
    character_dir = settings.AUDIO_BASE_DIR / character_slug / lang
    character_dir.mkdir(parents=True, exist_ok=True)
    
    # Audio filename (language included in path, not filename for compatibility)
    audio_filename = f"{topic}_{scene_index}.wav"
    audio_path = character_dir / audio_filename
    
    # Skip if exists
    if skip_existing and audio_path.exists() and audio_path.stat().st_size > 0:
        print(f"  ⏭️  {audio_filename} exists, skipping")
        return False
    
    # Clean text
    cleaned_text = clean_text_for_tts(scene_text, character_slug)
    if not cleaned_text or len(cleaned_text.strip()) < 5:
        print(f"  ⚠️  Empty or too short text, skipping")
        return False
    
    try:
        # Generate TTS with character-specific voice
        audio_bytes = await generate_tts_with_elevenlabs(
            text=cleaned_text,
            voice=character_slug,  # Use character slug for voice lookup
            emotion=char_voice.get("emotion", "calm"),
            speed=char_voice.get("speed", 0.85),
            pitch=char_voice.get("pitch", 0.95),
            topic=topic
        )
        
        if audio_bytes and len(audio_bytes) > 100:
            # Determine file extension
            is_mp3 = audio_bytes[:3] == b'ID3' or audio_bytes[:2] == b'\xff\xfb'
            audio_ext = '.mp3' if is_mp3 else '.wav'
            
            # Update filename with correct extension
            # Language is already in path: {character}/{lang}/{topic}_{scene_index}.ext
            audio_filename = f"{topic}_{scene_index}{audio_ext}"
            audio_path = character_dir / audio_filename
            
            # Save audio file
            with open(audio_path, 'wb') as f:
                f.write(audio_bytes)
            
            file_size_kb = len(audio_bytes) / 1024
            print(f"  ✅ Generated: {audio_filename} ({file_size_kb:.1f} KB)")
            return True
        else:
            print(f"  ❌ Failed to generate audio (empty or too small)")
            return False
            
    except Exception as e:
        print(f"  ❌ Error generating audio: {e}")
        return False


async def generate_audios_for_character(
    character_name: str,
    character_slug: str,
    lang: Optional[str] = None,
    topic: Optional[str] = None,
    skip_existing: bool = False
):
    """Generate audio files for a character."""
    char_voice = get_character_voice_settings(character_slug)
    print(f"\n🎤 {character_name} ({character_slug})")
    print(f"   Voice: {char_voice.get('voice', 'unknown')}")
    print(f"   Emotion: {char_voice.get('emotion', 'unknown')}")
    print(f"   Speed: {char_voice.get('speed', 1.0)}")
    print(f"   Pitch: {char_voice.get('pitch', 1.0)}")
    print(f"   Original: {char_voice.get('original_inspiration', 'unknown')}")
    
    langs_to_process = [lang] if lang else LANGS
    topics_to_process = [topic] if topic else TOPICS
    
    total_generated = 0
    total_skipped = 0
    total_failed = 0
    
    for lang_code in langs_to_process:
        for topic_name in topics_to_process:
            # Load story
            story = load_story(lang_code, character_slug, topic_name)
            if not story:
                continue
            
            # Get scenes
            scenes = story.get("scenes", [])
            if not scenes:
                continue
            
            print(f"\n  📖 {topic_name} ({lang_code}) - {len(scenes)} scenes")
            
            for scene_idx, scene in enumerate(scenes):
                scene_text = scene.get("text", "")
                if not scene_text:
                    continue
                
                success = await generate_audio_for_scene(
                    character_slug=character_slug,
                    topic=topic_name,
                    scene_index=scene_idx,
                    scene_text=scene_text,
                    lang=lang_code,
                    skip_existing=skip_existing
                )
                
                if success:
                    total_generated += 1
                elif skip_existing:
                    total_skipped += 1
                else:
                    total_failed += 1
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)
    
    print(f"\n  ✅ {character_name}: Generated={total_generated}, Skipped={total_skipped}, Failed={total_failed}")
    return total_generated, total_skipped, total_failed


async def main():
    parser = argparse.ArgumentParser(description="Generate TTS audio files from story JSON files")
    parser.add_argument("--character", help="Specific character slug (e.g., mino, luna)")
    parser.add_argument("--lang", help="Specific language (e.g., en, tr, de, es, fr)")
    parser.add_argument("--topic", help="Specific topic (e.g., bedtime, behavior)")
    parser.add_argument("--skip-existing", action="store_true", help="Skip existing audio files")
    parser.add_argument("--all", action="store_true", help="Generate for all visible characters")
    
    args = parser.parse_args()
    
    # Check FAL_API_KEY
    settings = Settings()
    if not settings.FAL_API_KEY:
        print("❌ FAL_API_KEY not found in environment")
        print("   Please set FAL_API_KEY in .env file or environment")
        sys.exit(1)
    
    # Determine characters to process
    if args.character:
        # Find character by slug
        characters_to_process = [
            (name, slug) for name, slug in VISIBLE_CHARACTERS
            if slug.lower() == args.character.lower()
        ]
        if not characters_to_process:
            print(f"❌ Character '{args.character}' not found in visible characters")
            sys.exit(1)
    elif args.all:
        characters_to_process = VISIBLE_CHARACTERS
    else:
        print("❌ Please specify --character SLUG or --all")
        print(f"   Available characters: {', '.join([slug for _, slug in VISIBLE_CHARACTERS])}")
        sys.exit(1)
    
    print(f"🚀 Generating audio files for {len(characters_to_process)} character(s)")
    if args.lang:
        print(f"   Language: {args.lang}")
    if args.topic:
        print(f"   Topic: {args.topic}")
    if args.skip_existing:
        print(f"   ⏭️  Skipping existing files")
    print()
    
    total_generated = 0
    total_skipped = 0
    total_failed = 0
    
    for character_name, character_slug in characters_to_process:
        gen, skip, fail = await generate_audios_for_character(
            character_name=character_name,
            character_slug=character_slug,
            lang=args.lang,
            topic=args.topic,
            skip_existing=args.skip_existing
        )
        total_generated += gen
        total_skipped += skip
        total_failed += fail
    
    print("\n" + "="*60)
    print(f"✅ Total: Generated={total_generated}, Skipped={total_skipped}, Failed={total_failed}")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())

