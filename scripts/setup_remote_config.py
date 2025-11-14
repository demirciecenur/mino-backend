#!/usr/bin/env python3
"""
Firebase Remote Config Setup Script
Automatically creates Remote Config parameters for character visibility management.

Usage:
    python backend/scripts/setup_remote_config.py [--all-characters]

Environment:
    FIREBASE_SERVICE_ACCOUNT_PATH must be set or use default: firebase-service-account.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import firebase_admin
    from firebase_admin import credentials
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    import requests
except ImportError:
    print("❌ Required packages not installed.")
    print("   Install with: pip install firebase-admin google-auth requests")
    sys.exit(1)

from config.settings import Settings

# 14 Popüler Original Karakterler (İlk Sürüm)
POPULAR_CHARACTERS = [
    # Original characters (6)
    ("Mino", "mino"),
    ("Luna", "luna"),
    ("Tiko", "tiko"),
    ("Bubu", "bubu"),
    ("Sunny", "sunny"),
    ("Koko", "koko"),
    # Popular derivative characters (8)
    ("Sneaky Cat Tom", "tom"),
    ("Clever Mouse Jerry", "jerry"),
    ("Elisa the Ice Fairy", "elsa"),
    ("Shell Heroes Crew", "ninjaturtles"),
    ("Spider Fighter", "spiderman"),
    ("Yellow Buddy", "minion"),
    ("Chirpy Birdie", "tweety"),
    ("Bubble Buddy", "spongebob"),
]

# Tüm karakterler (ileride eklenecek)
ALL_CHARACTERS = [
    # Original characters
    ("Mino", "mino"),
    ("Luna", "luna"),
    ("Tiko", "tiko"),
    ("Bubu", "bubu"),
    ("Sunny", "sunny"),
    ("Koko", "koko"),
    # Derivative characters
    ("Sneaky Cat Tom", "tom"),
    ("Clever Mouse Jerry", "jerry"),
    ("Elisa the Ice Fairy", "elsa"),
    ("Shell Heroes Crew", "ninjaturtles"),
    ("Spider Fighter", "spiderman"),
    ("Yellow Buddy", "minion"),
    ("Chirpy Birdie", "tweety"),
    ("Bubble Buddy", "spongebob"),
    ("Funny Bunny", "bugsbunny"),
    ("Super Metal Hero", "ironman"),
    ("Piggy Friend", "peppapig"),
    ("Blu Pup", "bluey"),
    ("Rescue Pup Crew", "pawpatrol"),
    ("Ocean Dreamer Moa", "moana"),
    ("Super Jump Hero", "mario"),
    ("Swamp Buddy Hero", "shrek"),
    ("Boots Knight Pal", "pussinboots"),
    ("Frost Friend Sid", "sid"),
    ("Adventure Dora Pal", "dora"),
    ("Snowman Buddy Olaf-style", "olaf"),
    ("Spark Buddy", "pikachu"),
    ("Mystery Pup Buddy", "scoobydoo"),
    ("Winnie", "winnie"),
    ("Bunny", "bunny"),
]


def initialize_firebase() -> bool:
    """Initialize Firebase Admin SDK."""
    try:
        if firebase_admin._apps:
            print("✅ Firebase already initialized")
            return True
        
        settings = Settings()
        cred_path = Path(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
        
        if not cred_path.exists():
            print(f"❌ Firebase service account not found: {cred_path}")
            print("   Please download from Firebase Console and place at:")
            print(f"   {cred_path.absolute()}")
            return False
        
        cred = credentials.Certificate(str(cred_path))
        firebase_admin.initialize_app(cred)
        print("✅ Firebase Admin SDK initialized")
        return True
    except Exception as e:
        print(f"❌ Firebase initialization failed: {e}")
        return False


def create_remote_config_template(
    characters: List[Tuple[str, str]], 
    include_hard_blocking: bool = True,
    popular_characters: List[Tuple[str, str]] = None
) -> Dict:
    """Create Remote Config template with all parameters.
    
    Args:
        characters: All characters to create parameters for
        include_hard_blocking: Whether to create hard blocking parameters
        popular_characters: List of popular characters that should be visible (invisible=false)
                           If None, all characters default to visible (false)
    """
    parameters = {}
    
    # Popular character slugs for default visibility
    popular_slugs = set()
    if popular_characters:
        popular_slugs = {slug for _, slug in popular_characters}
    
    # 1. Policy Version
    parameters["rc_policy_version"] = {
        "defaultValue": {
            "value": "0"
        },
        "valueType": "NUMBER",
        "description": "Policy version for cache busting - increment when making visibility changes"
    }
    
    # 2. Soft Blocking (Invisible) - Her karakter için
    for display_name, slug in characters:
        key = f"rc_force_invisible_{slug}"
        # Popular characters are visible (false), others are invisible (true)
        default_value = "false" if slug in popular_slugs else "true"
        parameters[key] = {
            "defaultValue": {
                "value": default_value
            },
            "valueType": "BOOLEAN",
            "description": f"Hide {display_name} from UI (soft blocking). Default: {'visible' if default_value == 'false' else 'hidden'}"
        }
    
    # 3. Hard Blocking (Blocked) - Opsiyonel
    if include_hard_blocking:
        for display_name, slug in characters:
            key = f"rc_force_blocked_{slug}"
            parameters[key] = {
                "defaultValue": {
                    "value": "false"
                },
                "valueType": "BOOLEAN",
                "description": f"Block {display_name} storage access (hard blocking)"
            }
    
    return {
        "parameters": parameters,
        "conditions": [],
        "version": {
            "description": "Initial Remote Config setup for character visibility management"
        }
    }


def get_access_token(cred_path: Path) -> str:
    """Get OAuth2 access token for Firebase REST API."""
    credentials_obj = service_account.Credentials.from_service_account_file(
        str(cred_path),
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    credentials_obj.refresh(Request())
    return credentials_obj.token


def publish_remote_config(template: Dict, project_id: str, cred_path: Path) -> bool:
    """Publish Remote Config template to Firebase using REST API."""
    try:
        # Get access token
        print("🔐 Authenticating with Firebase...")
        access_token = get_access_token(cred_path)
        
        # Get current template
        url = f"https://firebaseremoteconfig.googleapis.com/v1/projects/{project_id}/remoteConfig"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        print("📋 Fetching current Remote Config template...")
        response = requests.get(url, headers=headers)
        
        etag = None
        if response.status_code == 404:
            # Template doesn't exist yet, create new one
            print("📝 No existing template found, creating new one...")
            current_template = {
                "parameters": {},
                "conditions": [],
                "version": {
                    "versionNumber": "1",
                    "updateTime": "",
                    "updateUser": {}
                }
            }
        elif response.status_code == 200:
            current_template = response.json()
            version_num = current_template.get('version', {}).get('versionNumber', 'unknown')
            print(f"📋 Current template version: {version_num}")
            # Get ETag from response headers for If-Match
            etag = response.headers.get('ETag')
            if etag:
                print(f"📋 ETag: {etag}")
        else:
            print(f"❌ Failed to fetch current template: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
        
        # Merge new parameters into current template
        if "parameters" not in current_template:
            current_template["parameters"] = {}
        
        for key, param in template["parameters"].items():
            if key in current_template["parameters"]:
                print(f"⚠️  Parameter '{key}' already exists, updating...")
            else:
                print(f"➕ Adding parameter '{key}'...")
            
            # Convert our format to Firebase format
            current_template["parameters"][key] = {
                "defaultValue": param["defaultValue"],
                "valueType": param["valueType"]
            }
            if "description" in param:
                current_template["parameters"][key]["description"] = param["description"]
        
        # Update version
        if "version" not in current_template:
            current_template["version"] = {}
        
        # Publish template with If-Match header for version control
        print("\n🚀 Publishing Remote Config template...")
        publish_headers = headers.copy()
        if etag:
            # Use ETag for optimistic concurrency control
            publish_headers['If-Match'] = etag
            print(f"📋 Using ETag for version control: {etag}")
        else:
            # For new templates, use If-None-Match: *
            publish_headers['If-None-Match'] = '*'
            print("📋 Creating new template (If-None-Match: *)")
        
        response = requests.put(url, headers=publish_headers, json=current_template)
        
        if response.status_code == 200:
            published_template = response.json()
            print(f"✅ Template published successfully!")
            version = published_template.get("version", {})
            print(f"   Version: {version.get('versionNumber', 'unknown')}")
            print(f"   Updated: {version.get('updateTime', 'unknown')}")
            print(f"   Total parameters: {len(published_template.get('parameters', {}))}")
            return True
        else:
            print(f"❌ Failed to publish template: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to publish Remote Config: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Setup Firebase Remote Config for character visibility")
    parser.add_argument(
        "--all-characters",
        action="store_true",
        help="Include all characters (default: only 14 popular characters)"
    )
    parser.add_argument(
        "--no-hard-blocking",
        action="store_true",
        help="Skip hard blocking parameters (only create soft blocking)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without publishing"
    )
    
    args = parser.parse_args()
    
    # Select characters
    if args.all_characters:
        characters = ALL_CHARACTERS
        print(f"📋 Using ALL characters ({len(characters)} total)")
    else:
        characters = POPULAR_CHARACTERS
        print(f"📋 Using 14 POPULAR characters (first release)")
    
    print("\n📝 Characters to configure:")
    for i, (name, slug) in enumerate(characters, 1):
        print(f"   {i:2d}. {name:25s} → {slug}")
    
    # Initialize Firebase
    settings = Settings()
    cred_path = Path(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
    
    # Check multiple possible locations
    possible_paths = [
        cred_path,  # From settings (default: firebase-service-account.json in root)
        Path(__file__).parent.parent / "firebase-service-account.json",  # backend/firebase-service-account.json
        Path(__file__).parent.parent.parent / "firebase-service-account.json",  # root/firebase-service-account.json
    ]
    
    cred_path = None
    for path in possible_paths:
        if path.exists():
            cred_path = path
            print(f"✅ Found service account: {path}")
            break
    
    if not cred_path or not cred_path.exists():
        print(f"❌ Firebase service account not found in any of these locations:")
        for path in possible_paths:
            print(f"   - {path.absolute()}")
        print("\n   Please download from Firebase Console and place at one of these locations")
        sys.exit(1)
    
    # Get project ID from service account
    try:
        with open(cred_path, 'r') as f:
            service_account_data = json.load(f)
            project_id = service_account_data.get("project_id")
            if not project_id:
                print("❌ Could not find project_id in service account file")
                sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to read service account file: {e}")
        sys.exit(1)
    
    print(f"📦 Firebase Project ID: {project_id}")
    
    # Create template
    print("\n🔨 Creating Remote Config template...")
    
    # If using all characters, pass popular characters for default visibility
    popular_for_defaults = POPULAR_CHARACTERS if args.all_characters else None
    
    template = create_remote_config_template(
        characters,
        include_hard_blocking=not args.no_hard_blocking,
        popular_characters=popular_for_defaults
    )
    
    total_params = len(template["parameters"])
    print(f"✅ Template created with {total_params} parameters")
    print(f"   - 1 policy version")
    print(f"   - {len(characters)} soft blocking (invisible)")
    
    # Show visibility breakdown
    if args.all_characters and popular_for_defaults:
        popular_slugs = {slug for _, slug in popular_for_defaults}
        visible_count = sum(1 for _, slug in characters if slug in popular_slugs)
        hidden_count = len(characters) - visible_count
        print(f"     • {visible_count} visible (popular characters)")
        print(f"     • {hidden_count} hidden (others)")
    
    if not args.no_hard_blocking:
        print(f"   - {len(characters)} hard blocking (blocked)")
    
    # Dry run
    if args.dry_run:
        print("\n🔍 DRY RUN - Template preview:")
        print(json.dumps(template, indent=2))
        print("\n⚠️  Use without --dry-run to publish")
        return
    
    # Publish
    if not publish_remote_config(template, project_id, cred_path):
        sys.exit(1)
    
    print("\n✅ Remote Config setup complete!")
    print("\n📋 Next steps:")
    print("   1. Go to Firebase Console → Remote Config")
    print("   2. Verify all parameters are created")
    print("   3. Test by setting rc_force_invisible_mino = true")
    print("   4. Increment rc_policy_version = 1")
    print("   5. Publish and test in app")


if __name__ == "__main__":
    main()

