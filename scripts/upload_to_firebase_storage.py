#!/usr/bin/env python3
"""
Upload videos and profile images to Firebase Cloud Storage.

Güncel Action Set (6 Essential Actions):
- wave (wave_greeting + wave_goodbye birleşti)
- talking
- raise_hand
- hand_on_hip
- lean_closer
- side_glance

14 Visible Characters (MVP):
- Mino, Luna, Tiko, Bubu, Sunny, Koko
- Sneaky Cat Tom (tom), Clever Mouse Jerry (jerry)
- Elisa the Ice Fairy (elsa), Shell Heroes Crew (ninjaturtles)
- Spider Fighter (spiderman), Yellow Buddy (minion)
- Chirpy Birdie (tweety), Bubble Buddy (spongebob)

Usage:
    python backend/scripts/upload_to_firebase_storage.py [--videos-only] [--profiles-only] [--character CHARACTER] [--version VERSION]
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import Settings
import firebase_admin
from firebase_admin import credentials, storage

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VIDEOS_DIR = PROJECT_ROOT / "mino" / "Assets" / "characters"
PROFILES_DIR = PROJECT_ROOT / "mino" / "Assets" / "characters"

# 14 Visible Characters (MVP)
VISIBLE_CHARACTERS = [
    "mino", "luna", "tiko", "bubu", "sunny", "koko",
    "tom", "jerry", "elsa", "ninjaturtles",
    "spiderman", "minion", "tweety", "spongebob"
]


def upload_video(character: str, action: str, video_path: Path, version: str = "v1") -> bool:
    """Upload a video file to Firebase Storage."""
    try:
        bucket = storage.bucket()
        
        # Storage path: video/{character}/{action}_v{version}.mp4 (structured)
        storage_path = f"video/{character.lower()}/{action}_{version}.mp4"
        blob = bucket.blob(storage_path)
        
        # Set metadata
        blob.metadata = {
            "character": character,
            "action": action,
            "version": version,
            "content_type": "video/mp4"
        }
        
        # Set cache control (1 year)
        blob.cache_control = "public, max-age=31536000, immutable"
        
        # Upload file
        blob.upload_from_filename(str(video_path))
        
        # Make public (or use signed URLs for security)
        blob.make_public()
        
        print(f"✅ Uploaded: {storage_path} ({video_path.stat().st_size / 1024 / 1024:.1f} MB)")
        return True
    except Exception as e:
        print(f"❌ Failed to upload {video_path}: {e}")
        return False


def upload_profile(character: str, profile_path: Path, version: str = "v1") -> bool:
    """Upload a profile image to Firebase Storage."""
    try:
        bucket = storage.bucket()
        
        # Storage path: profile/{character}_v{version}.{ext} (structured)
        ext = profile_path.suffix.lower()
        storage_path = f"profile/{character.lower()}_{version}{ext}"
        blob = bucket.blob(storage_path)
        
        # Set metadata
        blob.metadata = {
            "character": character,
            "version": version,
            "content_type": f"image/{ext[1:]}"  # Remove dot
        }
        
        # Set cache control (1 year)
        blob.cache_control = "public, max-age=31536000, immutable"
        
        # Upload file
        blob.upload_from_filename(str(profile_path))
        
        # Make public (or use signed URLs for security)
        blob.make_public()
        
        print(f"✅ Uploaded: {storage_path} ({profile_path.stat().st_size / 1024:.1f} KB)")
        return True
    except Exception as e:
        print(f"❌ Failed to upload {profile_path}: {e}")
        return False


# Güncel action set (6 essential actions)
ESSENTIAL_ACTIONS = ["wave", "talking", "raise_hand", "hand_on_hip", "lean_closer", "side_glance"]

# Legacy action mappings (eski isimler → yeni isimler)
ACTION_MAPPING = {
    "wave_greeting": "wave",
    "wave_goodbye": "wave",
    "foot_tap": "side_glance",  # Legacy action
    "storytelling": "hand_on_hip",  # Legacy action
    "listen": "side_glance",  # Legacy action
    "speak": "talking",  # Legacy action
    "idle": "talking",  # Legacy action
}


def normalize_action(action: str) -> str:
    """Normalize action name to current action set."""
    action_lower = action.lower()
    
    # Direct match
    if action_lower in ESSENTIAL_ACTIONS:
        return action_lower
    
    # Check mapping
    if action_lower in ACTION_MAPPING:
        return ACTION_MAPPING[action_lower]
    
    # Return as-is if not found (will be filtered later)
    return action_lower


def find_character_videos(character: str) -> list[tuple[str, Path]]:
    """Find all video files for a character and map to current action set."""
    character_dir = VIDEOS_DIR / character.lower()
    if not character_dir.exists():
        return []
    
    videos = []
    for video_file in character_dir.glob("*.mp4"):
        # Extract action from filename (e.g., "mino_wave.mp4" -> "wave")
        # or "koko_wave_greeting.mp4" -> "wave_greeting" -> "wave"
        filename = video_file.stem
        action = filename.replace(f"{character.lower()}_", "")
        
        # Normalize to current action set
        normalized_action = normalize_action(action)
        
        # Only include if it's in the essential actions list
        if normalized_action in ESSENTIAL_ACTIONS:
            videos.append((normalized_action, video_file))
        else:
            print(f"⚠️  Skipping legacy action: {action} (normalized: {normalized_action})")
    
    return videos


def find_character_profile(character: str) -> Optional[Path]:
    """Find profile image for a character."""
    character_dir = PROFILES_DIR / character.lower()
    if not character_dir.exists():
        return None
    
    # Try common profile image names
    for pattern in [f"{character.lower()}_profile.*", f"{character.lower()}_profile_.*"]:
        for profile_file in character_dir.glob(pattern):
            if profile_file.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                return profile_file
    
    return None


def main():
    parser = argparse.ArgumentParser(description="Upload videos and profiles to Firebase Storage")
    parser.add_argument("--videos-only", action="store_true", help="Upload only videos")
    parser.add_argument("--profiles-only", action="store_true", help="Upload only profiles")
    parser.add_argument("--character", help="Specific character to upload")
    parser.add_argument("--version", default="v1", help="Version tag (default: v1)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded without uploading")
    
    args = parser.parse_args()
    
    # Initialize Firebase
    settings = Settings()
    if not settings.FIREBASE_PROJECT_ID:
        print("❌ FIREBASE_PROJECT_ID not found")
        sys.exit(1)
    
    # Initialize Firebase Admin SDK if not already initialized
    try:
        if not firebase_admin._apps:
            # Check multiple possible locations for service account
            cred_path = Path(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
            possible_paths = [
                cred_path,  # From settings
                Path(__file__).parent.parent / "firebase-service-account.json",  # backend/
                Path(__file__).parent.parent.parent / "firebase-service-account.json",  # root
            ]
            
            cred_path = None
            for path in possible_paths:
                if path.exists():
                    cred_path = path
                    break
            
            if not cred_path or not cred_path.exists():
                print(f"❌ Firebase service account not found")
                print("   Please download from Firebase Console and place at:")
                for path in possible_paths:
                    print(f"   {path.absolute()}")
                sys.exit(1)
            
            cred = credentials.Certificate(str(cred_path))
            firebase_admin.initialize_app(cred, {
                'storageBucket': settings.FIREBASE_STORAGE_BUCKET
            })
            print("✅ Firebase Admin SDK initialized")
        else:
            print("✅ Firebase already initialized")
    except Exception as e:
        print(f"❌ Firebase initialization failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Characters to process
    if args.character:
        characters = [args.character.lower()]
    else:
        # MVP: Only visible characters
        characters = [char for char in VISIBLE_CHARACTERS if (VIDEOS_DIR / char).exists()]
        print(f"📋 Processing {len(characters)} visible characters for MVP")
    
    print(f"🚀 Uploading to Firebase Storage (version: {args.version})")
    if args.dry_run:
        print("   [DRY RUN MODE - No files will be uploaded]")
    print()
    
    total_videos = 0
    total_profiles = 0
    
    for character in characters:
        print(f"📦 {character}")
        
        # Upload videos
        if not args.profiles_only:
            videos = find_character_videos(character)
            for action, video_path in videos:
                if args.dry_run:
                    print(f"   [DRY RUN] Would upload: video/{character.lower()}/{action}_{args.version}.mp4")
                else:
                    if upload_video(character, action, video_path, args.version):
                        total_videos += 1
        
        # Upload profile
        if not args.videos_only:
            profile_path = find_character_profile(character)
            if profile_path:
                if args.dry_run:
                    print(f"   [DRY RUN] Would upload: profile/{character.lower()}_{args.version}{profile_path.suffix}")
                else:
                    if upload_profile(character, profile_path, args.version):
                        total_profiles += 1
            else:
                print(f"   ⚠️  Profile image not found for {character}")
        
        print()
    
    print("="*60)
    print(f"✅ Upload complete: {total_videos} videos, {total_profiles} profiles")
    print("="*60)


if __name__ == "__main__":
    main()

