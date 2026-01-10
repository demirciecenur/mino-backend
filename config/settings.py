"""Application settings and constants."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Settings:
    """Application settings and configuration."""
    
    # API Keys
    FAL_API_KEY: str = os.getenv('FAL_API_KEY', '')
    ELEVENLABS_API_KEY: str = os.getenv('ELEVENLABS_API_KEY', '')
    OPENAI_API_KEY: str = os.getenv('OPENAI_API_KEY', '')
    TTS_PROVIDER: str = os.getenv('TTS_PROVIDER', 'fal')  # fal | elevenlabs
    TTS_FAL_MODEL: str = os.getenv('TTS_FAL_MODEL', 'fal-ai/elevenlabs/tts/eleven-v3')
    FCM_SERVER_KEY: str = os.getenv('FCM_SERVER_KEY', '')  # Firebase Cloud Messaging Server Key
    
    # App Store Receipt Verification
    APP_STORE_SHARED_SECRET: str = os.getenv('APP_STORE_SHARED_SECRET', '')  # App Store Shared Secret for receipt verification
    APP_STORE_VERIFY_RECEIPT_SANDBOX: str = "https://sandbox.itunes.apple.com/verifyReceipt"
    APP_STORE_VERIFY_RECEIPT_PRODUCTION: str = "https://buy.itunes.apple.com/verifyReceipt"
    
    # RevenueCat Configuration
    REVENUECAT_SECRET_API_KEY: str = os.getenv('REVENUECAT_SECRET_API_KEY', '')  # RevenueCat Secret API Key for backend verification
    
    # Firebase Configuration
    FIREBASE_STORAGE_BUCKET: str = os.getenv('FIREBASE_STORAGE_BUCKET', 'mino-mobile-app-firebase.appspot.com')
    FIREBASE_PROJECT_ID: str = os.getenv('FIREBASE_PROJECT_ID', '')
    # Firebase service account path: try relative to backend/ directory, then current directory
    _firebase_path_rel = Path(__file__).parent.parent / "firebase-service-account.json"
    _firebase_path_cur = Path("firebase-service-account.json")
    FIREBASE_SERVICE_ACCOUNT_PATH: str = str(_firebase_path_rel if _firebase_path_rel.exists() else _firebase_path_cur)
    FIREBASE_FIRESTORE_DATABASE: str = os.getenv('FIREBASE_FIRESTORE_DATABASE', 'mino')  # Firestore database name
    
    # Backend Base URL for audio URLs (used by iOS app)
    # Production: https://64.226.88.203 (or domain if configured)
    # Development: http://127.0.0.1:8000
    # CRITICAL: Never use localhost in production - always use production IP or domain
    _backend_url = os.getenv('BACKEND_BASE_URL', 'https://64.226.88.203')
    # Sanitize: Replace localhost/127.0.0.1 with production URL if detected
    if '127.0.0.1' in _backend_url or 'localhost' in _backend_url:
        print(f"⚠️ [Settings] WARNING: BACKEND_BASE_URL contains localhost: {_backend_url}")
        print(f"   Replacing with production URL: https://64.226.88.203")
        _backend_url = 'https://64.226.88.203'
    BACKEND_BASE_URL: str = _backend_url
    
    # Audio Storage Paths
    # Note: Audio files are stored in backend/storage/characters (based on backend logs)
    # Backend logs show: /Users/ecenurgezsat/Projects/mino/backend/storage/characters/luna/en/bedtime_0.wav
    # Production: /home/app/app/storage/characters (no "backend" prefix)
    # Development: /home/app/backend/storage/characters (with "backend" prefix)
    @property
    def AUDIO_BASE_DIR(self) -> Path:
        """Get audio base directory.
        
        Production: /home/app/app/storage/characters
        Development: backend/storage/characters (if exists)
        """
        # __file__ is: backend/config/settings.py (dev) or /home/app/app/config/settings.py (prod)
        config_dir = Path(__file__).resolve().parent  # config/
        app_dir = config_dir.parent  # app/ (prod) or backend/ (dev)
        
        # Try production path first: app/storage/characters
        prod_path = app_dir / "storage" / "characters"
        if prod_path.exists():
            print(f"✅ [Settings] AUDIO_BASE_DIR resolved: {prod_path} (production path)")
            return prod_path
        
        # Fallback: check if we're in backend/ directory structure
        # This handles development where files might be in backend/storage/characters
        backend_storage = app_dir.parent / "backend" / "storage" / "characters"
        if backend_storage.exists():
            print(f"✅ [Settings] AUDIO_BASE_DIR resolved: {backend_storage} (development path)")
            return backend_storage
        
        # Default: return production path (will be created if needed)
        print(f"⚠️ [Settings] AUDIO_BASE_DIR path does not exist, using default: {prod_path}")
        print(f"   Config dir: {config_dir}")
        print(f"   App dir: {app_dir}")
        print(f"   Production path: {prod_path}")
        print(f"   Backend storage path: {backend_storage}")
        return prod_path
    
    # CORS Settings
    CORS_ORIGINS: list = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://64.226.88.203",  # Production: DigitalOcean Droplet (FRA1) - Nginx proxy on port 80
        "http://64.226.88.203:8000",  # Production: Direct access (if firewall allows)
        "https://api.mino.app",  # Production: Domain (if configured)
    ]
    
    # Character Voice Settings (Storyteller for Kids)
    # All characters read stories as engaging storytellers for children
    # Voice settings match original character inspiration from CHARACTER_PERSONALITY
    # Speed is slower for clarity, pitch is child-friendly, emotion matches original character tone
    CHARACTER_VOICES = {
        # Original characters
        "mino": {
            "voice": "child-friendly",
            "emotion": "calm",  # Calm storyteller for bedtime stories
            "speed": 0.85,  # Slower pace for clear storytelling
            "pitch": 0.95,  # Slightly lower, soothing pitch
            "voice_id": "AZnzlk1XvdvUeBnXmlld",
            "storyteller": True,
            "original_inspiration": "Mino"
        },
        "luna": {
            "voice": "female-bright",
            "emotion": "cheerful",  # Smurfette-inspired: magical, dreamy, cheerful
            "speed": 1.0,  # Normal speed for 5-year-old child voice
            "pitch": 1.0,  # Use natural pitch of child voice
            "voice_id": "ocZQ262SsZb9RIxcQBOj",  # Girl (5-year-old child voice)
            "storyteller": True,
            "original_inspiration": "Smurfs Smurfette"
        },
        "bubu": {
            "voice": "female-soft",
            "emotion": "sad",  # Inside-Out Sadness-inspired: soft, sad but loving (girl character)
            "speed": 0.75,  # Slower for melancholic, gentle delivery
            "pitch": 0.92,  # Soft pitch for empathetic, gentle girl voice (Inside Out Sadness)
            "voice_id": "ocZQ262SsZb9RIxcQBOj",  # Girl (5-year-old child voice) - soft, empathetic, perfect for Inside Out Sadness
            "storyteller": True,
            "original_inspiration": "Inside Out Sadness"
        },
        "tiko": {
            "voice": "female-bright",
            "emotion": "energetic",  # Adventurous, energetic, brave - 2-8 year old girl voice
            "speed": 1.0,  # Normal speed for 5-year-old child voice
            "pitch": 1.05,  # Slightly higher pitch for energetic, playful tone (2-8 year old girl)
            "voice_id": "hO2yZ8lxM3axUxL8OeKX",  # Girl (5-year-old child voice) - perfect for Tiko
            "storyteller": True,
            "original_inspiration": "Tiko - Adventurous girl character"
        },
        "masha": {  # Alias for Tiko
            "voice": "female-bright",
            "emotion": "energetic",
            "speed": 1.0,
            "pitch": 1.05,
            "voice_id": "hO2yZ8lxM3axUxL8OeKX",  # Girl (5-year-old child voice) - same as Tiko
            "storyteller": True,
            "original_inspiration": "Tiko - Adventurous girl character"
        },
        "sunny": {
            "voice": "female-bright",
            "emotion": "cheerful",  # Cheerful storyteller
            "speed": 1.0,  # Normal speed for 5-year-old child voice
            "pitch": 1.0,  # Use natural pitch of child voice
            "voice_id": "hO2yZ8lxM3axUxL8OeKX",  # Girl (5-year-old child voice)
            "storyteller": True,
            "original_inspiration": "Sunny"
        },
        "koko": {
            "voice": "male-young",
            "emotion": "determined",  # Batman-inspired: strong, protective, determined
            "speed": 1.0,  # Normal speed for 5-year-old child voice
            "pitch": 1.0,  # Use natural pitch of child voice
            "voice_id": "zYcjlYFOd3taleS0gkk3",  # Boy (5-year-old child voice)
            "storyteller": True,
            "original_inspiration": "Batman"
        },
        # Derivative characters (ASO-safe names) - mapped to original character voices
        "elisa the ice fairy": {
            "voice": "female-soft",
            "emotion": "calm",  # Frozen Elsa-inspired
            "speed": 0.88,
            "pitch": 1.0,
            "voice_id": "XB0fDUnXU5powFXDhCwa",  # Charlotte - Soft, graceful female voice (perfect for Elsa)
            "storyteller": True,
            "original_inspiration": "Frozen Elsa"
        },
        "spider fighter": {
            "voice": "male-young",
            "emotion": "energetic",  # Spiderman-inspired: brave, adventurous, cheerful
            "speed": 0.95,  # Slightly slower for child-friendly pace
            "pitch": 1.0,  # Normal pitch for cheerful, adventurous tone
            "voice_id": "yoZ06aMxZJJ28mfd3POQ",  # Sam - Young, energetic male voice (perfect for Spiderman)
            "storyteller": True,
            "original_inspiration": "Spiderman"
        },
        "yellow buddy": {
            "voice": "child-friendly",
            "emotion": "cheerful",  # Minions-inspired: funny, cheerful, playful
            "speed": 1.1,  # Faster for funny, playful tone
            "pitch": 1.05,  # Higher for comedic, fun tone
            "voice_id": "AZnzlk1XvdvUeBnXmlld",
            "storyteller": True,
            "original_inspiration": "Minions"
        },
        "chirpy birdie": {
            "voice": "female-bright",
            "emotion": "cheerful",  # Tweety Bird-inspired: sweet, cute, cheerful
            "speed": 0.95,  # Normal pace
            "pitch": 1.1,  # Higher pitch for sweet, cute tone
            "voice_id": "21m00Tcm4TlvDq8ikWAM",  # Rachel - High-pitched, sweet female voice (perfect for Tweety)
            "storyteller": True,
            "original_inspiration": "Tweety Bird"
        },
        "bubble buddy": {
            "voice": "child-friendly",
            "emotion": "cheerful",  # SpongeBob-inspired: cheerful, energetic, optimistic
            "speed": 1.05,  # Faster for energetic, optimistic tone
            "pitch": 1.0,  # Normal pitch
            "voice_id": "AZnzlk1XvdvUeBnXmlld",
            "storyteller": True,
            "original_inspiration": "SpongeBob"
        },
        "tom": {
            "voice": "male-young",
            "emotion": "playful",  # Tom Cat-inspired: playful, funny, energetic
            "speed": 1.0,  # Normal speed for 5-year-old child voice
            "pitch": 1.0,  # Use natural pitch of child voice
            "voice_id": "87n4zM8Wuy87vFILuKvE",  # Young Energetic Boy (5-year-old child voice)
            "storyteller": True,
            "original_inspiration": "Tom Cat"
        },
        "sneaky cat tom": {
            "voice": "male-young",
            "emotion": "playful",
            "speed": 1.0,  # Normal speed for 5-year-old child voice
            "pitch": 1.0,  # Use natural pitch of child voice
            "voice_id": "87n4zM8Wuy87vFILuKvE",  # Young Energetic Boy (5-year-old child voice)
            "storyteller": True,
            "original_inspiration": "Tom Cat"
        },
        "jerry": {
            "voice": "male-young",
            "emotion": "clever",  # Jerry Mouse-inspired: clever, small but brave, playful
            "speed": 1.0,  # Normal speed for 5-year-old child voice
            "pitch": 1.0,  # Use natural pitch of child voice
            "voice_id": "xtPlXcRNvdlUVw2QsITM",  # Boy (5-year-old child voice)
            "storyteller": True,
            "original_inspiration": "Jerry Mouse"
        },
        "clever mouse jerry": {
            "voice": "male-young",
            "emotion": "clever",
            "speed": 1.0,  # Normal speed for 5-year-old child voice
            "pitch": 1.0,  # Use natural pitch of child voice
            "voice_id": "xtPlXcRNvdlUVw2QsITM",  # Boy (5-year-old child voice)
            "storyteller": True,
            "original_inspiration": "Jerry Mouse"
        },
        "elsa": {
            "voice": "female-soft",
            "emotion": "calm",  # Frozen Elsa-inspired: magical, graceful, calm
            "speed": 0.88,
            "pitch": 1.0,
            "voice_id": "XB0fDUnXU5powFXDhCwa",  # Charlotte - Soft, graceful female voice (perfect for Elsa)
            "storyteller": True,
            "original_inspiration": "Frozen Elsa"
        },
        "ninjaturtles": {
       
            "emotion": "determined",  # Brave, but child-friendly
            "speed": 1.0,  # Slightly quicker for youthful energy
            "pitch": 1.05,  # Higher pitch for young male tone
            #"voice_id": "TxGEqnHWrfWFTfGW9XjX",  # Josh - young male voice
            "voice": "Daniel",
            "storyteller": True,
            "original_inspiration": "Ninja Turtles"
        },
        "shell heroes crew": {
         
            "emotion": "determined",
            "speed": 0.95,
            "pitch": 0.90,
            #"voice_id": "VR6AewLTigWG4xSOukaG",  # Arnold - Warm, determined male voice
            "voice": "Daniel",
            "storyteller": True,
            "original_inspiration": "Ninja Turtles"
        },
        "spiderman": {
            "voice": "male-young",
            "emotion": "energetic",  # Spiderman-inspired: brave, adventurous, cheerful
            "speed": 0.95,  # Slightly slower for child-friendly pace
            "pitch": 1.0,  # Normal pitch for cheerful, adventurous tone
            "voice_id": "yoZ06aMxZJJ28mfd3POQ",  # Sam - Young, energetic male voice (perfect for Spiderman)
            "storyteller": True,
            "original_inspiration": "Spiderman"
        },
        "minion": {
            "voice": "child-friendly",
            "emotion": "cheerful",  # Minions-inspired: funny, cheerful, playful
            "speed": 1.15,  # Faster for funny, playful tone (Minions speak quickly)
            "pitch": 1.15,  # Higher pitch for comedic, fun tone (Minions have distinctive high-pitched voice)
            "voice_id": "AZnzlk1XvdvUeBnXmlld",  # Domi - child-friendly, can be adjusted with higher pitch
            "storyteller": True,
            "original_inspiration": "Minions"
        },
        "tweety": {
            "voice": "female-bright",
            "emotion": "cheerful",  # Tweety Bird-inspired: sweet, cute, cheerful
            "speed": 1.0,  # Normal speed for 5-year-old child voice
            "pitch": 1.0,  # Use natural pitch of child voice
            "voice_id": "ocZQ262SsZb9RIxcQBOj",  # Lulu Lollipop - Sweet & Bubbly Girl (5-year-old child voice)
            "storyteller": True,
            "original_inspiration": "Tweety Bird"
        },
        "spongebob": {
            "voice": "male-young",
            "emotion": "cheerful",  # SpongeBob-inspired: cheerful, energetic, optimistic
            "speed": 1.15,  # Faster speed for energetic, cheerful tone
            "pitch": 1.0,  # Use natural pitch of child voice
            "voice_id": "VE5rsMNTeE1frCCSXNIC",  # Boy (5-year-old child voice)
            "storyteller": True,
            "original_inspiration": "SpongeBob"
        },
        "funny bunny": {
            "voice": "male-warm",
            "emotion": "cheerful",  # Bugs Bunny-inspired: clever, funny, confident
            "speed": 1.0,  # Normal pace
            "pitch": 0.95,  # Slightly higher for clever, confident tone
            "voice_id": "VR6AewLTigWG4xSOukaG",
            "storyteller": True,
            "original_inspiration": "Bugs Bunny"
        },
        "super metal hero": {
            "voice": "male-warm",
            "emotion": "confident",  # Iron Man-inspired: intelligent, technological, confident
            "speed": 0.9,  # Slightly slower for intelligent, confident tone
            "pitch": 0.9,  # Lower for strong, confident voice
            "voice_id": "VR6AewLTigWG4xSOukaG",
            "storyteller": True,
            "original_inspiration": "Iron Man"
        },
        "piggy friend": {
            "voice": "female-bright",
            "emotion": "cheerful",  # Peppa Pig-inspired: cheerful, playful, family-focused
            "speed": 0.95,  # Normal pace
            "pitch": 1.05,  # Higher for cute, cheerful tone
            "voice_id": "EXAVITQu4vr4xnSDxMaL",
            "storyteller": True,
            "original_inspiration": "Peppa Pig"
        },
        "blu pup": {
            "voice": "female-bright",
            "emotion": "cheerful",  # Bluey-inspired: cheerful, playful, creative
            "speed": 0.95,  # Normal pace
            "pitch": 1.0,  # Normal pitch
            "voice_id": "EXAVITQu4vr4xnSDxMaL",
            "storyteller": True,
            "original_inspiration": "Bluey"
        },
        "rescue pup crew": {
            "voice": "male-warm",
            "emotion": "determined",  # Paw Patrol-inspired: brave, helpful, heroic
            "speed": 0.95,  # Normal pace
            "pitch": 0.95,  # Slightly lower for brave, heroic tone
            "voice_id": "VR6AewLTigWG4xSOukaG",
            "storyteller": True,
            "original_inspiration": "Paw Patrol"
        },
        "ocean dreamer moa": {
            "voice": "female-bright",
            "emotion": "determined",  # Moana-inspired: brave, adventurous, strong
            "speed": 0.95,  # Normal pace
            "pitch": 1.0,  # Normal pitch
            "voice_id": "EXAVITQu4vr4xnSDxMaL",
            "storyteller": True,
            "original_inspiration": "Moana"
        },
        "super jump hero": {
            "voice": "male-warm",
            "emotion": "energetic",  # Mario-inspired: brave, adventurous, playful
            "speed": 1.0,  # Normal pace
            "pitch": 0.95,  # Slightly higher for playful, cheerful tone
            "voice_id": "VR6AewLTigWG4xSOukaG",
            "storyteller": True,
            "original_inspiration": "Mario"
        },
        "swamp buddy hero": {
            "voice": "male-warm",
            "emotion": "cheerful",  # Shrek-inspired: strong, funny, loving
            "speed": 0.9,  # Slightly slower
            "pitch": 0.88,  # Lower for strong, authentic tone
            "voice_id": "VR6AewLTigWG4xSOukaG",
            "storyteller": True,
            "original_inspiration": "Shrek"
        },
        "boots knight pal": {
            "voice": "male-warm",
            "emotion": "confident",  # Puss in Boots-inspired: brave, graceful, confident
            "speed": 0.95,  # Normal pace
            "pitch": 0.95,  # Slightly lower for confident, graceful tone
            "voice_id": "VR6AewLTigWG4xSOukaG",
            "storyteller": True,
            "original_inspiration": "Puss in Boots"
        },
        "frost friend sid": {
            "voice": "male-warm",
            "emotion": "cheerful",  # Ice Age Sid-inspired: funny, cheerful, friendly
            "speed": 1.0,  # Normal pace
            "pitch": 0.95,  # Slightly higher for funny, friendly tone
            "voice_id": "VR6AewLTigWG4xSOukaG",
            "storyteller": True,
            "original_inspiration": "Ice Age Sid"
        },
        "adventure dora pal": {
            "voice": "female-bright",
            "emotion": "energetic",  # Dora the Explorer-inspired: adventurous, curious, learning-loving
            "speed": 1.0,  # Normal pace
            "pitch": 1.05,  # Higher for curious, energetic tone
            "voice_id": "EXAVITQu4vr4xnSDxMaL",
            "storyteller": True,
            "original_inspiration": "Dora the Explorer"
        },
        "snowman buddy olaf-style": {
            "voice": "child-friendly",
            "emotion": "cheerful",  # Frozen Olaf-inspired: cheerful, innocent, cute
            "speed": 1.0,  # Normal pace
            "pitch": 1.1,  # Higher for innocent, cute tone
            "voice_id": "AZnzlk1XvdvUeBnXmlld",
            "storyteller": True,
            "original_inspiration": "Frozen Olaf"
        },
        "spark buddy": {
            "voice": "child-friendly",
            "emotion": "energetic",  # Pikachu-inspired: cheerful, energetic, cute
            "speed": 1.05,  # Faster for energetic tone
            "pitch": 1.1,  # Higher for cute, energetic tone
            "voice_id": "AZnzlk1XvdvUeBnXmlld",
            "storyteller": True,
            "original_inspiration": "Pikachu"
        },
        "mystery pup buddy": {
            "voice": "male-warm",
            "emotion": "cheerful",  # Scooby-Doo-inspired: funny, scared but brave, friendly
            "speed": 0.95,  # Normal pace
            "pitch": 0.95,  # Slightly lower for friendly, comedic tone
            "voice_id": "VR6AewLTigWG4xSOukaG",
            "storyteller": True,
            "original_inspiration": "Scooby-Doo"
        },
        "sneaky cat tom": {
            "voice": "male-warm",
            "emotion": "cheerful",  # Tom and Jerry-inspired: playful, funny, clever
            "speed": 1.0,  # Normal pace
            "pitch": 0.95,  # Slightly higher for playful, clever tone
            "voice_id": "VR6AewLTigWG4xSOukaG",
            "storyteller": True,
            "original_inspiration": "Tom and Jerry"
        },
        "clever mouse jerry": {
            "voice": "male-young",
            "emotion": "clever",  # Tom and Jerry-inspired: clever, small but brave, playful
            "speed": 1.0,  # Normal speed for 5-year-old child voice
            "pitch": 1.0,  # Use natural pitch of child voice
            "voice_id": "87n4zM8Wuy87vFILuKvE",  # Young Energetic Boy (5-year-old child voice)
            "storyteller": True,
            "original_inspiration": "Tom and Jerry"
        },
        "shell heroes crew": {
            "voice": "male-warm",
            "emotion": "determined",  # Teenage Mutant Ninja Turtles-inspired: brave, teamwork, heroic
            "speed": 0.95,  # Normal pace
            "pitch": 0.95,  # Slightly lower for brave, heroic tone
            "voice_id": "VR6AewLTigWG4xSOukaG",
            "storyteller": True,
            "original_inspiration": "Teenage Mutant Ninja Turtles"
        },
        "tinnie": {
            "voice": "male-warm",
            "emotion": "calm",  # Winnie the Pooh-inspired: sweet, cute, honey-loving, friendly
            "speed": 0.85,  # Slower for sweet, calm tone
            "pitch": 0.9,  # Lower for warm, friendly tone
            "voice_id": "pNInz6obpgDQGcFmaJgB",
            "storyteller": True,
            "original_inspiration": "Winnie the Pooh"
        },
    }
    
    # Voice Mapping (ElevenLabs voice IDs)
    VOICE_MAPPING = {
        "gender-neutral-mid": "AZnzlk1XvdvUeBnXmlld",  # Domi
        "female-bright": "EXAVITQu4vr4xnSDxMaL",       # Bella
        "female-soft": "XB0fDUnXU5powFXDhCwa",         # Charlotte
        "male-warm": "VR6AewLTigWG4xSOukaG",          # Arnold
        "male-gentle": "VR6AewLTigWG4xSOukaG",        # Arnold
        "male-deep": "ThT5KcBeYPX3keUQqHPh",          # Antoni (deep, mature)
        "male-young": "TxGEqnHWrfWFTfGW9XjX",         # Josh (young, energetic)
        "child-friendly": "AZnzlk1XvdvUeBnXmlld",     # Domi
        
        # Character-specific (from CHARACTER_VOICES voice_id)
        "mino": "AZnzlk1XvdvUeBnXmlld",  # Domi
        "luna": "MF3mGyEYCl7XYWbV9V6O",  # Elli (young, bright female)
        "tiko": "hO2yZ8lxM3axUxL8OeKX",  # Girl (5-year-old child voice) - energetic, adventurous girl
        "masha": "hO2yZ8lxM3axUxL8OeKX",  # Girl (5-year-old child voice) - same as Tiko
        "bubu": "pNInz6obpgDQGcFmaJgB",  # Adam (deep, empathetic)
        "sunny": "EXAVITQu4vr4xnSDxMaL",  # Bella (bright, cheerful)
        "koko": "ThT5KcBeYPX3keUQqHPh",  # Antoni (deep, mature - Batman)
        "tom": "pNInz6obpgDQGcFmaJgB",  # Adam
        "sneaky cat tom": "pNInz6obpgDQGcFmaJgB",  # Adam
        "bunny": "pNInz6obpgDQGcFmaJgB",  # Adam
        "elsa": "XB0fDUnXU5powFXDhCwa",  # Charlotte (soft, graceful)
        "elisa the ice fairy": "XB0fDUnXU5powFXDhCwa",  # Charlotte
        "jerry": "21m00Tcm4TlvDq8ikWAM",  # Rachel (high-pitched, clever)
        "clever mouse jerry": "21m00Tcm4TlvDq8ikWAM",  # Rachel
        "ninja turtles": "VR6AewLTigWG4xSOukaG",  # Arnold (warm, determined)
        "ninjaturtles": "VR6AewLTigWG4xSOukaG",  # Arnold
        "shell heroes crew": "VR6AewLTigWG4xSOukaG",  # Arnold
        "tweety": "21m00Tcm4TlvDq8ikWAM",  # Rachel (high-pitched, sweet)
        "chirpy birdie": "21m00Tcm4TlvDq8ikWAM",  # Rachel
        "spiderman": "yoZ06aMxZJJ28mfd3POQ",  # Sam (young, energetic)
        "spider fighter": "yoZ06aMxZJJ28mfd3POQ",  # Sam
        "minion": "AZnzlk1XvdvUeBnXmlld",  # Domi (child-friendly)
        "yellow buddy": "AZnzlk1XvdvUeBnXmlld",  # Domi
        "spongebob": "AZnzlk1XvdvUeBnXmlld",  # Domi
        "bubble buddy": "AZnzlk1XvdvUeBnXmlld",  # Domi
        "winnie": "pNInz6obpgDQGcFmaJgB",  # Adam
    }
    
    # Character-Topic Settings (optimized for storyteller narration)
    # Storyteller style: Higher style values (0.5-0.7) for dramatic, expressive storytelling
    # Stability: Slightly lower (0.6-0.8) for more natural, engaging narration
    # Similarity boost: High (0.8-0.9) to maintain character voice consistency
    CHARACTER_TOPIC_SETTINGS = {
        # Mino - Storyteller for Kids (calm, soothing bedtime stories)
        "mino_sleep": {"stability": 0.75, "similarity_boost": 0.9, "style": 0.6},  # Expressive, calm storyteller
        "mino_homework": {"stability": 0.7, "similarity_boost": 0.85, "style": 0.55},  # Encouraging storyteller
        "mino_creativity": {"stability": 0.65, "similarity_boost": 0.8, "style": 0.65},  # Excited, creative storyteller
        "mino_sad": {"stability": 0.8, "similarity_boost": 0.9, "style": 0.5},  # Gentle, comforting storyteller
        
        # Default storyteller settings for all characters
        "default_storyteller": {"stability": 0.7, "similarity_boost": 0.85, "style": 0.6},
        
        # Add more character-topic combinations as needed
        "luna_sleep": {"stability": 0.75, "similarity_boost": 0.9, "style": 0.6},
        "bubu_sleep": {"stability": 0.78, "similarity_boost": 0.9, "style": 0.5},  # calmer, sad tone
        "tiko_sleep": {"stability": 0.7, "similarity_boost": 0.85, "style": 0.65},
        "sunny_sleep": {"stability": 0.75, "similarity_boost": 0.85, "style": 0.6},
        "koko_sleep": {"stability": 0.7, "similarity_boost": 0.85, "style": 0.6},
        "elsa_bedtime": {"stability": 0.75, "similarity_boost": 0.9, "style": 0.6},  # Magical, graceful storyteller
        "elsa_sleep": {"stability": 0.75, "similarity_boost": 0.9, "style": 0.6},
        
        # 5-year-old child voices - using real child voices from ElevenLabs
        # Natural child voice settings: moderate stability, good similarity, expressive style
        "tweety_bedtime": {"stability": 0.50, "similarity_boost": 0.75, "style": 0.70},  # 5-year-old girl voice (Lulu Lollipop)
        "tweety": {"stability": 0.50, "similarity_boost": 0.75, "style": 0.70},  # Default for all topics - 5-year-old girl voice
        "spongebob_bedtime": {"stability": 0.50, "similarity_boost": 0.75, "style": 0.70},  # 5-year-old boy voice (Young Energetic Boy)
        "spongebob": {"stability": 0.50, "similarity_boost": 0.75, "style": 0.70},  # Default for all topics - 5-year-old boy voice
        "tom_bedtime": {"stability": 0.50, "similarity_boost": 0.75, "style": 0.70},  # 5-year-old boy voice (Young Energetic Boy)
        "tom": {"stability": 0.50, "similarity_boost": 0.75, "style": 0.70},  # Default for all topics - 5-year-old boy voice
        "jerry_bedtime": {"stability": 0.50, "similarity_boost": 0.75, "style": 0.70},  # 5-year-old boy voice (Young Energetic Boy)
        "jerry": {"stability": 0.50, "similarity_boost": 0.75, "style": 0.70},  # Default for all topics - 5-year-old boy voice
        "clever mouse jerry_bedtime": {"stability": 0.50, "similarity_boost": 0.75, "style": 0.70},  # 5-year-old boy voice (Young Energetic Boy)
        "clever mouse jerry": {"stability": 0.50, "similarity_boost": 0.75, "style": 0.70},  # Default for all topics - 5-year-old boy voice
    }
    
    @classmethod
    def ensure_directories(cls):
        """Ensure required directories exist."""
        # AUDIO_BASE_DIR is now a property, so we need to get the instance first
        settings = cls()
        settings.AUDIO_BASE_DIR.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Get application settings instance."""
    settings = Settings()
    settings.ensure_directories()
    return settings
