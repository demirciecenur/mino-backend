#!/usr/bin/env python3
"""
Create public seed stories for HomeView (Most Liked & Last Created sections).

This script creates 4 public stories per language:
- 2 stories for "Most Liked" section
- 2 stories for "Last Created" section

Usage:
    python backend/scripts/create_public_stories.py --lang tr
    python backend/scripts/create_public_stories.py --lang en --dry-run
    python backend/scripts/create_public_stories.py --all-languages
"""

import os
import sys
import json
import argparse
import time
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Allow running from repo root or backend dir
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Load .env file
env_path = os.path.join(BACKEND_DIR, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"✅ Loaded .env from: {env_path}")
else:
    parent_env = os.path.join(os.path.dirname(BACKEND_DIR), ".env")
    if os.path.exists(parent_env):
        load_dotenv(parent_env)
        print(f"✅ Loaded .env from: {parent_env}")
    else:
        print(f"⚠️  No .env file found at {env_path} or {parent_env}")

# Debug: Check if Firebase API key is loaded
firebase_api_key_debug = os.getenv("FIREBASE_API_KEY") or os.getenv("FIREBASE_WEB_API_KEY")
if firebase_api_key_debug:
    print(f"✅ FIREBASE_API_KEY found: {firebase_api_key_debug[:10]}...")
else:
    print(f"⚠️  FIREBASE_API_KEY not found. Available env vars with 'FIREBASE':")
    for key in os.environ.keys():
        if 'FIREBASE' in key.upper():
            print(f"   - {key}")

# Import Firebase and story generation functions
import firebase_admin
from firebase_admin import credentials, firestore
from config.firebase_config import get_firebase_config

# Import story generation functions from main.py
# We need to import the async functions, so we'll use a different approach
# Import settings first
from config import get_settings
settings = get_settings()

# Import utilities
from utils.topic_mapping import map_topic
from services.story_composer import to_character_slug

# We'll use the API endpoint approach: create stories via POST /stories/custom
# But for seed stories, we can also directly write to Firestore after generating
# For now, let's use a simpler approach: call the story generation functions directly
# by importing main module functions
import httpx
import asyncio
import json
import os
import requests
import sys

# Initialize Firebase
firebase_config = get_firebase_config()
db = firebase_config.db

# Public story configurations per language
# Each language has 4 stories: 2 for "Most Liked", 2 for "Last Created"
PUBLIC_STORY_CONFIGS = {
    "tr": {
        "most_liked": [
            {
                "character": "Mino",
                "topic": "bedtime",
                "title": "Mino ile Uykuyu Sevdiren Yolculuk",
                "custom_description": "Yatma reddini azaltan, sakinleşme + rutin + 'yatağa geçiş' için ikna hikayesi.",
                "length": "quick"
            },
            {
                "character": "Luna",
                "topic": "tantrums",
                "title": "Luna ve Büyük Duygular: Öfke Nöbeti Sakinleştirme",
                "custom_description": "İsyan/bağırma/ağlama anında duyguyu adlandırma ve sakinleşme adımlarını öğreten hikaye.",
                "length": "quick"
            }
        ],
        "last_created": [
            {
                "character": "Bubu",
                "topic": "picky_eating",
                "title": "Bubu Yeni Tatları Dener",
                "custom_description": "Yemek seçmeyi yumuşatan: küçük deneme, baskısız yaklaşım, cesaretlendirme.",
                "length": "quick"
            },
            {
                "character": "Sunny",
                "topic": "potty_training",
                "title": "Sunny Tuvalet Kahramanı",
                "custom_description": "Tuvalet eğitiminde korku/direnç yaşayan çocuk için adım adım güven veren hikaye.",
                "length": "quick"
            }
        ]
    },
    "en": {
        "most_liked": [
            {
                "character": "Mino",
                "topic": "bedtime",
                "title": "Mino's Sleep-Time Mission",
                "custom_description": "A gentle bedtime story that reduces resistance and builds a calming routine.",
                "length": "quick"
            },
            {
                "character": "Luna",
                "topic": "tantrums",
                "title": "Luna and Big Feelings: Calm Down Magic",
                "custom_description": "Helps with tantrums: name feelings, breathe, choose a safe way to express anger.",
                "length": "quick"
            }
        ],
        "last_created": [
            {
                "character": "Bubu",
                "topic": "picky_eating",
                "title": "Bubu Tries One Tiny Bite",
                "custom_description": "For picky eating: no pressure, one tiny bite, praise courage, keep it playful.",
                "length": "quick"
            },
            {
                "character": "Sunny",
                "topic": "potty_training",
                "title": "Sunny's Potty Hero Story",
                "custom_description": "For potty training resistance: confidence, readiness, small wins, no shame.",
                "length": "quick"
            }
        ]
    },
    "de": {
        "most_liked": [
            {
                "character": "Mino",
                "topic": "bedtime",
                "title": "Minos Schlaf-Mission",
                "custom_description": "Sanfte Einschlafgeschichte gegen Widerstand, mit beruhigender Routine.",
                "length": "quick"
            },
            {
                "character": "Luna",
                "topic": "tantrums",
                "title": "Luna und große Gefühle: Wut wird leise",
                "custom_description": "Hilft bei Wutanfällen: Gefühle benennen, atmen, sichere Wahlmöglichkeiten.",
                "length": "quick"
            }
        ],
        "last_created": [
            {
                "character": "Bubu",
                "topic": "picky_eating",
                "title": "Bubu probiert einen Mini-Bissen",
                "custom_description": "Für wählerisches Essen: ohne Druck, spielerisch, kleine Mut-Schritte.",
                "length": "quick"
            },
            {
                "character": "Sunny",
                "topic": "potty_training",
                "title": "Sunnys Töpfchen-Heldenmut",
                "custom_description": "Für Töpfchen-Training: Angst abbauen, kleine Erfolge, ohne Scham.",
                "length": "quick"
            }
        ]
    },
    "es": {
        "most_liked": [
            {
                "character": "Mino",
                "topic": "bedtime",
                "title": "La Misión de Dormir de Mino",
                "custom_description": "Una historia suave para reducir la resistencia y crear rutina de sueño.",
                "length": "quick"
            },
            {
                "character": "Luna",
                "topic": "tantrums",
                "title": "Luna y las Emociones Grandes: Calma en 3 Pasos",
                "custom_description": "Para berrinches: nombrar emoción, respirar, elegir una forma segura de expresarse.",
                "length": "quick"
            }
        ],
        "last_created": [
            {
                "character": "Bubu",
                "topic": "picky_eating",
                "title": "Bubu Prueba un Mordisquito",
                "custom_description": "Para comer selectivo: sin presión, un mordisco pequeño, reforzar valentía.",
                "length": "quick"
            },
            {
                "character": "Sunny",
                "topic": "potty_training",
                "title": "Sunny, Héroe del Baño",
                "custom_description": "Para dejar el pañal: confianza, señales de preparación, pasos pequeños.",
                "length": "quick"
            }
        ]
    },
    "fr": {
        "most_liked": [
            {
                "character": "Mino",
                "topic": "bedtime",
                "title": "La Mission Dodo de Mino",
                "custom_description": "Une histoire douce pour réduire le refus du coucher et installer une routine.",
                "length": "quick"
            },
            {
                "character": "Luna",
                "topic": "tantrums",
                "title": "Luna et les Grandes Émotions : On se Calme Ensemble",
                "custom_description": "Pour les crises: nommer l'émotion, respirer, choisir un geste sûr.",
                "length": "quick"
            }
        ],
        "last_created": [
            {
                "character": "Bubu",
                "topic": "picky_eating",
                "title": "Bubu Goûte un Tout Petit Morceau",
                "custom_description": "Pour le tri alimentaire: sans pression, mini-bouchée, encourager le courage.",
                "length": "quick"
            },
            {
                "character": "Sunny",
                "topic": "potty_training",
                "title": "Sunny, Héros du Pot",
                "custom_description": "Pour l'apprentissage du pot: confiance, petits pas, zéro honte.",
                "length": "quick"
            }
        ]
    }
}


def generate_story_id(character: str, topic: str, lang: str, section: str, index: int) -> str:
    """Generate deterministic story ID for public stories."""
    # Format: public_{section}_{lang}_{character}_{topic}_{index}
    character_slug = to_character_slug(character)
    topic_slug = map_topic(topic.lower())
    return f"public_{section}_{lang}_{character_slug}_{topic_slug}_{index}"


async def create_public_story(config: dict, lang: str, section: str, index: int, dry_run: bool = False):
    """Create a single public story with full text and audio generation using direct function calls."""
    character = config["character"]
    topic = config["topic"]
    title = config["title"]
    custom_description = config.get("custom_description", "")
    length = config.get("length", "quick")
    
    character_slug = to_character_slug(character)
    topic_mapped = map_topic(topic.lower())
    
    story_id = generate_story_id(character, topic, lang, section, index)
    
    print(f"\n📖 Creating public story:")
    print(f"   ID: {story_id}")
    print(f"   Character: {character} ({character_slug})")
    print(f"   Topic: {topic} → {topic_mapped}")
    print(f"   Language: {lang}")
    print(f"   Section: {section}")
    print(f"   Title: {title}")
    
    if dry_run:
        print(f"   [DRY RUN] Would create full story with text and audio")
        return story_id
    
    # Import story generation functions directly from main.py
    # This avoids API authentication issues and works offline
    try:
        # Import main module functions
        sys.path.insert(0, BACKEND_DIR)
        from models.story_create_models import StoryRequest
        from main import generate_story_async, generate_custom_story_id
        
        print(f"   🚀 Generating full story with text and audio (direct function call)...")
        print(f"   📍 Audio will be saved to: {settings.AUDIO_BASE_DIR}/{character_slug}/{lang}/")
        
        # Use public_seed as user_id (special admin user for public stories)
        admin_user_id = "public_seed"
        
        # Create StoryRequest object
        # CRITICAL: Use character_slug (normalized) to ensure character-specific voice settings are used
        # The character_slug will be passed to generate_tts, which will look up CHARACTER_VOICES
        # to get character-specific voice_id, emotion, speed, and pitch settings
        story_request = StoryRequest(
            character_id=character_slug,  # Normalized character slug (e.g., "mino", "bubu", "luna", "sunny")
            topic=topic_mapped,
            language=lang,
            custom_description=custom_description,
            child_name=None,
            length=length,
            is_public=True
        )
        
        # DEBUG: Verify character slug will use character-specific voice
        print(f"   🎤 Character voice verification:")
        print(f"      Character: {character} → Slug: {character_slug}")
        print(f"      This slug will be used to look up CHARACTER_VOICES for character-specific voice settings")
        
        # ONE-TIME SCRIPT: Delete existing audio files for this story to force regeneration
        # CRITICAL SAFETY: Only delete audio files that match this specific story_id
        # Audio files are stored at: {AUDIO_BASE_DIR}/{character_slug}/{lang}/{topic}_{story_id}_{scene_index}.wav
        # Format: {topic}_{safe_story_suffix}_{scene_index}.wav where safe_story_suffix = story_id (without "story_" prefix)
        # For public stories: story_id = "public_most_liked_de_mino_bedtime_0"
        # Audio filename: "bedtime_public_most_liked_de_mino_bedtime_0_0.wav"
        audio_dir = Path(settings.AUDIO_BASE_DIR) / character_slug / lang
        if audio_dir.exists():
            # CRITICAL: Only delete files that match this specific story_id
            # Pattern must include full story_id to ensure we don't delete other stories' audio
            # Story ID format: public_{section}_{lang}_{character}_{topic}_{index}
            # Audio pattern: {topic}_{story_id}_*.wav
            audio_pattern = f"{topic_mapped}_{story_id}_*.wav"
            audio_pattern_mp3 = f"{topic_mapped}_{story_id}_*.mp3"
            deleted_count = 0
            deleted_files = []
            
            for audio_file in list(audio_dir.glob(audio_pattern)) + list(audio_dir.glob(audio_pattern_mp3)):
                # CRITICAL SAFETY CHECK: Verify filename contains the exact story_id
                # This ensures we only delete audio files for this specific public story
                # Story ID format: public_{section}_{lang}_{character}_{topic}_{index}
                # Audio filename format: {topic}_{story_id}_{scene_index}.wav
                # Example: "bedtime_public_most_liked_de_mino_bedtime_0_0.wav"
                if story_id in audio_file.name:
                    # TRIPLE CHECK: Verify story_id starts with "public_" (only our script's stories)
                    # This prevents accidentally deleting user-generated story audio files (story_*)
                    if story_id.startswith("public_"):
                        try:
                            audio_file.unlink()
                            deleted_count += 1
                            deleted_files.append(audio_file.name)
                            print(f"   🗑️  Deleted existing audio: {audio_file.name}")
                        except Exception as e:
                            print(f"   ⚠️  Could not delete {audio_file.name}: {e}")
                    else:
                        print(f"   ⚠️  Skipping audio file (not a public seed story, story_id doesn't start with 'public_'): {audio_file.name}")
                else:
                    print(f"   ⚠️  Skipping audio file (story_id mismatch): {audio_file.name}")
            
            if deleted_count > 0:
                print(f"   ✅ Deleted {deleted_count} existing audio file(s) for story '{story_id}' - will regenerate with character-specific voice")
                print(f"      Files deleted: {', '.join(deleted_files[:5])}{'...' if len(deleted_files) > 5 else ''}")
            else:
                print(f"   ℹ️  No existing audio files found for story '{story_id}' - will generate new audio")
        
        # Create story document first (same as API endpoint does)
        # Set created_at based on section
        if section == "most_liked":
            days_ago = 45 + (index * 5)
        else:
            days_ago = 2 + index
        
        created_at = time.time() - (days_ago * 24 * 60 * 60)
        
        # Create Firestore document with status="text_pending" (same as API endpoint)
        story_data = {
            "id": story_id,
            "title": f"Story about {topic_mapped[:50]}",  # Temporary title, will be updated by AI
            "status": "text_pending",  # Will transition: text_pending → audio_pending → ready
            "character_id": character_slug,
            "language": lang,
            "owner_user_id": admin_user_id,
            "topic": topic_mapped,
            "custom_description": custom_description,
            "child_name": None,
            "length_type": length,
            "kind": "custom",
            "is_public": True,
            "quota_counted": False,  # Public stories don't count against quota
            "created_at": created_at,
            "updated_at": time.time()
        }
        
        if db:
            story_ref = db.collection("stories").document(story_id)
            story_ref.set(story_data)
            print(f"   ✅ Created story document: {story_id}")
        
        # Start story generation (same as API endpoint does)
        # CRITICAL: In production, we need to await the generation to ensure it completes
        # For script execution, we'll run it synchronously to completion
        print(f"   📝 Starting story generation (text + audio)...")
        print(f"   ⏳ This may take 2-5 minutes per story (text generation + audio generation)...")
        
        # Run generation synchronously (await) so script waits for completion
        # This ensures all stories are fully generated before script exits
        try:
            await generate_story_async(story_id, story_request)
            
            # Verify story was fully generated by checking Firestore
            if db:
                story_doc = db.collection("stories").document(story_id).get()
                if story_doc.exists:
                    story_data = story_doc.to_dict()
                    story_status = story_data.get("status")
                    story_text = story_data.get("text") or story_data.get("generated_text")
                    scenes = story_data.get("scenes", [])
                    
                    if story_status == "ready" and story_text and scenes:
                        print(f"   ✅ Story generation completed: {story_id}")
                        print(f"   📊 Status: {story_status}, Text: {len(story_text)} chars, Scenes: {len(scenes)}")
                        print(f"   📁 Audio files saved to: {settings.AUDIO_BASE_DIR}/{character_slug}/{lang}/")
                        print(f"   🔗 Audio accessible via: {settings.BACKEND_BASE_URL}/local-audio/")
                    else:
                        print(f"   ⚠️  Story generation may be incomplete:")
                        print(f"      Status: {story_status}, Has text: {bool(story_text)}, Scenes: {len(scenes)}")
                        raise Exception(f"Story {story_id} not fully generated (status={story_status}, text={bool(story_text)}, scenes={len(scenes)})")
                else:
                    raise Exception(f"Story document {story_id} not found in Firestore")
            
            return story_id
        except Exception as gen_error:
            print(f"   ❌ Story generation failed for {story_id}: {gen_error}")
            import traceback
            traceback.print_exc()
            # Re-raise to stop script execution
            raise
        
    except ImportError as e:
        print(f"   ⚠️  Could not import main.py functions: {e}")
        print(f"   📝 Falling back to placeholder story")
        
        # Fallback: Create placeholder story
        if section == "most_liked":
            days_ago = 45 + (index * 5)
        else:
            days_ago = 2 + index
        
        created_at = time.time() - (days_ago * 24 * 60 * 60)
        placeholder_text = f"{title}. This is a public seed story for {section} section."
        
        story_data = {
            "id": story_id,
            "title": title,
            "text": placeholder_text,
            "status": "text_pending",
            "character_id": character_slug,
            "language": lang,
            "owner_user_id": "public_seed",
            "topic": topic_mapped,
            "custom_description": custom_description,
            "child_name": None,
            "length_type": length,
            "kind": "custom",
            "is_public": True,
            "quota_counted": False,
            "created_at": created_at,
            "updated_at": time.time(),
            "note": f"Public seed story - Generate via API: POST /stories/custom"
        }
        
        if db:
            story_ref = db.collection("stories").document(story_id)
            story_ref.set(story_data)
            print(f"   ✅ Created placeholder: {story_id}")
            print(f"   💡 Generate full story later via API endpoint")
    
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    return story_id


async def create_all_public_stories_for_language(lang: str, dry_run: bool = False, force_regenerate: bool = False):
    """
    Create all 4 public stories for a language.
    
    Args:
        lang: Language code (tr, en, de, es, fr)
        dry_run: If True, only print what would be created without actually creating
        force_regenerate: If True, delete existing public seed stories and audio files before regenerating
    """
    if lang not in PUBLIC_STORY_CONFIGS:
        print(f"❌ Language '{lang}' not supported. Supported: {list(PUBLIC_STORY_CONFIGS.keys())}")
        return []
    
    configs = PUBLIC_STORY_CONFIGS[lang]
    created_stories = []
    
    print(f"\n🌍 Creating public stories for language: {lang}")
    print(f"   Most Liked: {len(configs['most_liked'])} stories")
    print(f"   Last Created: {len(configs['last_created'])} stories")
    
    # CRITICAL SAFETY: Only delete stories created by this script (public seed stories)
    # Story IDs must start with "public_" and owner_user_id must be "public_seed"
    if force_regenerate and not dry_run:
        print(f"\n🔄 FORCE REGENERATE MODE: Will delete existing public seed stories and audio files for language: {lang}")
        if db:
            stories_ref = db.collection("stories")
            # CRITICAL: Only find stories created by this script
            # Filter: owner_user_id == "public_seed" AND language == lang AND id starts with "public_"
            public_stories = stories_ref.where("owner_user_id", "==", "public_seed")\
                                       .where("language", "==", lang)\
                                       .stream()
            
            deleted_count = 0
            deleted_story_ids = []
            for story_doc in public_stories:
                story_data = story_doc.to_dict()
                story_id = story_doc.id
                
                # DOUBLE CHECK: Only delete stories with "public_" prefix (created by this script)
                if not story_id.startswith("public_"):
                    print(f"   ⚠️  Skipping story (not a public seed story): {story_id}")
                    continue
                
                character_id = story_data.get("character_id", "")
                topic = story_data.get("topic", "")
                
                # Delete Firestore document
                story_doc.reference.delete()
                deleted_count += 1
                deleted_story_ids.append(story_id)
                print(f"   🗑️  Deleted Firestore document: {story_id}")
                
                # Delete audio files for this specific story only
                if character_id and topic:
                    audio_dir = Path(settings.AUDIO_BASE_DIR) / character_id / lang
                    if audio_dir.exists():
                        # CRITICAL: Only delete audio files matching this specific story_id
                        audio_pattern = f"{topic}_{story_id}_*.wav"
                        audio_pattern_mp3 = f"{topic}_{story_id}_*.mp3"
                        audio_deleted = 0
                        
                        for audio_file in list(audio_dir.glob(audio_pattern)) + list(audio_dir.glob(audio_pattern_mp3)):
                            # DOUBLE CHECK: Verify filename contains the exact story_id
                            if story_id in audio_file.name:
                                try:
                                    audio_file.unlink()
                                    audio_deleted += 1
                                    print(f"      🗑️  Deleted audio: {audio_file.name}")
                                except Exception as e:
                                    print(f"      ⚠️  Could not delete {audio_file.name}: {e}")
                        
                        if audio_deleted > 0:
                            print(f"      ✅ Deleted {audio_deleted} audio file(s) for story: {story_id}")
            
            if deleted_count > 0:
                print(f"\n   ✅ Deleted {deleted_count} existing public seed story document(s) and associated audio files")
                print(f"      Story IDs deleted: {', '.join(deleted_story_ids)}")
            else:
                print(f"\n   ℹ️  No existing public seed stories found for language: {lang}")
    
    # Create Most Liked stories
    for i, config in enumerate(configs["most_liked"]):
        story_id = await create_public_story(config, lang, "most_liked", i, dry_run)
        created_stories.append(story_id)
        if not dry_run:
            print(f"   ✅ Completed story {i+1}/{len(configs['most_liked'])} for 'Most Liked' section")
            if i < len(configs["most_liked"]) - 1:  # Don't wait after last story
                print(f"   ⏳ Waiting 3 seconds before next story...")
                await asyncio.sleep(3)  # Short wait between stories
    
    # Create Last Created stories
    for i, config in enumerate(configs["last_created"]):
        story_id = await create_public_story(config, lang, "last_created", i, dry_run)
        created_stories.append(story_id)
        if not dry_run:
            print(f"   ✅ Completed story {i+1}/{len(configs['last_created'])} for 'Last Created' section")
            if i < len(configs["last_created"]) - 1:  # Don't wait after last story
                print(f"   ⏳ Waiting 3 seconds before next story...")
                await asyncio.sleep(3)  # Short wait between stories
    
    return created_stories


async def main():
    parser = argparse.ArgumentParser(
        description="Create public seed stories for HomeView (one-time script)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run for Turkish (see what would be created)
  python backend/scripts/create_public_stories.py --lang tr --dry-run
  
  # Create stories for Turkish only
  python backend/scripts/create_public_stories.py --lang tr
  
  # Create stories for all languages (one-time setup)
  python backend/scripts/create_public_stories.py --all-languages
  
  # Force regenerate: delete existing stories and audio, then recreate
  python backend/scripts/create_public_stories.py --all-languages --force-regenerate
        """
    )
    parser.add_argument("--lang", help="Language code (tr, en, de, es, fr)")
    parser.add_argument("--all-languages", action="store_true", help="Create stories for all languages")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be created without actually creating")
    parser.add_argument("--force-regenerate", action="store_true", 
                       help="Delete existing stories and audio files before regenerating (one-time script mode)")
    args = parser.parse_args()
    
    if not args.lang and not args.all_languages:
        parser.print_help()
        print("\n❌ Error: Either --lang or --all-languages must be specified")
        return 1
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No stories will be created")
    
    if args.force_regenerate and not args.dry_run:
        print("🔄 FORCE REGENERATE MODE - Existing stories and audio will be deleted")
        response = input("⚠️  Are you sure you want to delete existing public stories? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Cancelled")
            return 1
    
    created_stories = []
    
    if args.all_languages:
        for lang in PUBLIC_STORY_CONFIGS.keys():
            print(f"\n{'='*60}")
            print(f"🌍 Processing language: {lang.upper()}")
            print(f"{'='*60}")
            stories = await create_all_public_stories_for_language(lang, args.dry_run, args.force_regenerate)
            created_stories.extend(stories)
            if not args.dry_run:
                print(f"   ✅ Completed all stories for language: {lang.upper()}")
                # Don't wait after last language
                if lang != list(PUBLIC_STORY_CONFIGS.keys())[-1]:
                    print(f"   ⏳ Waiting 5 seconds before next language...")
                    await asyncio.sleep(5)  # Short wait between languages
    else:
        stories = await create_all_public_stories_for_language(args.lang, args.dry_run, args.force_regenerate)
        created_stories.extend(stories)
    
    print(f"\n{'='*60}")
    print(f"✅ SUMMARY: Created {len(created_stories)} public stories")
    print(f"{'='*60}")
    if created_stories:
        print(f"   Story IDs:")
        for story_id in created_stories:
            print(f"   - {story_id}")
    
    print(f"\n📁 Audio files location:")
    print(f"   Production: {settings.AUDIO_BASE_DIR}")
    print(f"   Format: {{character}}/{{lang}}/{{topic}}_{{storyId}}_{{sceneIndex}}.wav")
    print(f"\n🔗 Audio access:")
    print(f"   URL: {settings.BACKEND_BASE_URL}/local-audio/{{character}}_{{topic}}_{{scene_index}}.wav?lang={{lang}}")
    print(f"\n✅ All stories are ready in Firestore with status='ready'")
    print(f"   Audio files are stored on server and accessible via /local-audio endpoint")
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

