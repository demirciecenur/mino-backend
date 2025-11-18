from fastapi import FastAPI, HTTPException, Response, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx
import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore, storage, auth
import ffmpeg
import tempfile
import uuid
from typing import Optional
import json
import hashlib
from datetime import datetime
import struct
import shutil
from pathlib import Path
import re
import time

# Import utilities
from utils.text_cleaner import clean_text_for_tts
from utils.audio_converter import convert_mp3_to_wav
from utils.audio_generator import generate_silent_audio


# Load environment variables
load_dotenv()

# Import settings and config
from config import get_settings
from config.firebase_config import get_firebase_config

# Initialize settings
settings = get_settings()
AUDIO_BASE_DIR = settings.AUDIO_BASE_DIR

# Initialize Firebase
firebase_config = get_firebase_config()
db = firebase_config.db
bucket = firebase_config.bucket

async def generate_tts_with_elevenlabs(text: str, voice: str, emotion: str, speed: float, pitch: float, topic: str = None) -> bytes:
    """Generate TTS using Direct ElevenLabs API (no fallback)"""
    try:
        # Get voice ID from CHARACTER_VOICES (character-specific) or VOICE_MAPPING (fallback)
        voice_lower = voice.lower()
        elevenlabs_voice = None
        
        # If provider override is set to FAL, delegate to FAL.ai TTS (ElevenLabs adapter)
        provider = (settings.TTS_PROVIDER or "elevenlabs").strip().lower()
        if provider == "fal":
            # Character-topic storyteller settings
            char_topic_key = f"{voice_lower}_{topic}" if topic else voice_lower
            char_settings = settings.CHARACTER_TOPIC_SETTINGS.get(
                char_topic_key,
                settings.CHARACTER_TOPIC_SETTINGS.get("default_storyteller", {"stability": 0.7, "similarity_boost": 0.85, "style": 0.6})
            )
            # Pass voice_id directly to FAL.ai (FAL.ai doesn't support generic voice types like "male-young")
            # Always use voice_id, not the generic "voice" field
            fal_voice = None
            char_voice_config = settings.CHARACTER_VOICES.get(voice_lower)
            if char_voice_config:
                voice_id = char_voice_config.get("voice_id")
                if voice_id:
                    # Try voice name first for voices that support it (only Rachel works with name)
                    voice_name_map = {
                        "21m00Tcm4TlvDq8ikWAM": "Rachel",  # Works with name
                        # Others need voice_id directly (Bella, Josh, etc.)
                    }
                    # For voices that work with name, use name; otherwise use ID
                    if voice_id in voice_name_map:
                        fal_voice = voice_name_map[voice_id]
                    else:
                        fal_voice = voice_id  # Use voice_id directly (e.g., "EXAVITQu4vr4xnSDxMaL" for Bella)
            if not fal_voice:
                # Fallback: try to get voice_id from VOICE_MAPPING
                voice_id_fallback = settings.VOICE_MAPPING.get(voice_lower)
                if voice_id_fallback:
                    voice_name_map = {
                        "21m00Tcm4TlvDq8ikWAM": "Rachel",
                    }
                    if voice_id_fallback in voice_name_map:
                        fal_voice = voice_name_map[voice_id_fallback]
                    else:
                        fal_voice = voice_id_fallback  # Use voice_id directly
            print(f"🎤 Using voice for {voice_lower}: {fal_voice} (voice_id from CHARACTER_VOICES)")
            return await _generate_tts_with_fal(text, char_settings, speed, pitch, fal_voice, character=voice_lower)
        
        # First, try to get from CHARACTER_VOICES (has character-specific voice_id)
        char_voice_config = settings.CHARACTER_VOICES.get(voice_lower)
        if char_voice_config and "voice_id" in char_voice_config:
            elevenlabs_voice = char_voice_config["voice_id"]
            print(f"✅ Found voice_id in CHARACTER_VOICES['{voice_lower}']: {elevenlabs_voice}")
        else:
            # Try case-insensitive match in CHARACTER_VOICES
            for key, value in settings.CHARACTER_VOICES.items():
                if key.lower() == voice_lower and "voice_id" in value:
                    elevenlabs_voice = value["voice_id"]
                    print(f"✅ Found voice_id in CHARACTER_VOICES (case-insensitive match '{key}'): {elevenlabs_voice}")
                    break
        
        # Fallback to VOICE_MAPPING if not found in CHARACTER_VOICES
        if not elevenlabs_voice:
            elevenlabs_voice = settings.VOICE_MAPPING.get(voice_lower, settings.VOICE_MAPPING.get("gender-neutral-mid", "AZnzlk1XvdvUeBnXmlld"))
            print(f"⚠️  Using VOICE_MAPPING fallback for '{voice_lower}': {elevenlabs_voice}")
        
        # Get character-topic specific settings for storyteller narration
        # Use storyteller-optimized settings for engaging, expressive story reading
        char_topic_key = f"{voice.lower()}_{topic}" if topic else voice.lower()
        char_settings = settings.CHARACTER_TOPIC_SETTINGS.get(
            char_topic_key, 
            settings.CHARACTER_TOPIC_SETTINGS.get(
                "default_storyteller", 
                {"stability": 0.7, "similarity_boost": 0.85, "style": 0.6}  # Storyteller defaults
            )
        )
        
        # Use Direct ElevenLabs API (required for reliable voice_id)
        elevenlabs_key = settings.ELEVENLABS_API_KEY.strip() if settings.ELEVENLABS_API_KEY else None
        if not elevenlabs_key:
            print("❌ ELEVENLABS_API_KEY not found, cannot generate TTS")
            return None
        
        print(f"🎯 Using Direct ElevenLabs API (more reliable for voice_id)")
        result = await _generate_tts_direct_elevenlabs(text, elevenlabs_voice, char_settings, speed, pitch)
        if result:
            return result
        # If direct API failed, return None (no fallback)
        print(f"❌ Direct ElevenLabs API failed, stopping")
        return None
            
    except Exception as e:
        print(f"❌ TTS generation failed: {e}")
        return None

# Text cleaning and audio conversion utilities are now imported from utils module

async def _generate_tts_with_fal(text: str, char_settings: dict, speed: float = 1.0, pitch: float = 1.0, voice_name_or_id: str = None, character: str = None) -> bytes:
    """Generate TTS via FAL.ai with multiple model fallbacks for child voices.
    
    If character has voice_cloning_reference, uses F5 TTS for voice cloning.
    Otherwise, uses standard ElevenLabs TTS models.
    """
    try:
        if not settings.FAL_API_KEY or not fal_client:
            print("❌ FAL_API_KEY not set or fal_client unavailable")
            return None
        
        # Check if character uses voice cloning
        use_voice_cloning = False
        reference_audio_path = None
        if character:
            char_voice_config = settings.CHARACTER_VOICES.get(character.lower())
            if char_voice_config and "voice_cloning_reference" in char_voice_config:
                ref_path = char_voice_config["voice_cloning_reference"]
                # Resolve path relative to backend directory
                backend_dir = Path(__file__).parent
                reference_audio_path = backend_dir / ref_path
                if reference_audio_path.exists():
                    use_voice_cloning = True
                    print(f"🎭 Using voice cloning for {character} with reference: {reference_audio_path}")
                else:
                    print(f"⚠️ Voice cloning reference not found: {reference_audio_path}, falling back to standard TTS")
        
        # Use F5 TTS for voice cloning
        if use_voice_cloning:
            try:
                # Upload reference audio
                print(f"📤 Uploading reference audio for voice cloning...")
                uploaded_file = fal_client.upload_file(str(reference_audio_path))
                print(f"✅ Reference audio uploaded: {uploaded_file}")
                
                # Generate with F5 TTS
                result = fal_client.submit(
                    "fal-ai/f5-tts",
                    arguments={
                        "gen_text": text,
                        "ref_audio_url": uploaded_file,
                        "model_type": "F5-TTS",
                        "output_format": "pcm_44100",
                    }
                )
                
                # Get result
                try:
                    output = result.get()
                except AttributeError:
                    output = result
                
                # Locate audio URL
                audio_url = None
                if isinstance(output, dict):
                    audio = output.get("audio")
                    if isinstance(audio, dict):
                        audio_url = audio.get("url")
                    elif isinstance(audio, str):
                        audio_url = audio
                    if not audio_url:
                        audio_url = output.get("audio_url") or output.get("output") or output.get("url")
                
                # If audio_url is a dict, extract the URL
                if isinstance(audio_url, dict):
                    audio_url = audio_url.get("url")
                
                if not audio_url or not isinstance(audio_url, str):
                    print(f"❌ No valid audio URL from F5 TTS, falling back to standard TTS")
                    use_voice_cloning = False
                else:
                    # Download audio
                    print(f"📥 Downloading cloned audio: {audio_url}")
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(audio_url, timeout=60.0)
                        resp.raise_for_status()
                        audio_bytes = resp.content
                    
                    if audio_bytes and len(audio_bytes) > 1000:
                        print(f"✅ Voice cloning successful: {len(audio_bytes)/1024:.1f} KB")
                        return audio_bytes
                    else:
                        print(f"⚠️ Cloned audio too small, falling back to standard TTS")
                        use_voice_cloning = False
            except Exception as e:
                print(f"⚠️ Voice cloning failed: {e}, falling back to standard TTS")
                use_voice_cloning = False
        
        # Fallback to standard TTS if voice cloning not used or failed
        if not use_voice_cloning:
            # For child voices (5 years), use very high pitch for thin, high-pitched voice
            # Normal speed, very high pitch (1.6+) for child-like voice
            speed_clamped = max(0.7, min(1.3, speed))
            pitch_clamped = max(0.5, min(2.0, pitch))  # Allow up to 2.0 for very high-pitched child voices
        
        # Try multiple FAL.ai models in order of preference
        models_to_try = [
            settings.TTS_FAL_MODEL,  # Current model (eleven-v3)
            "fal-ai/elevenlabs/tts/eleven-v3",  # Explicit v3 model
            "fal-ai/elevenlabs/tts/multilingual-v2",  # Alternative ElevenLabs model
            "fal-ai/elevenlabs/tts/turbo-v2.5",  # Alternative ElevenLabs model
        ]
        
        # Prepare base arguments
        base_arguments = {
            "text": text,
            **({"voice": voice_name_or_id} if voice_name_or_id else {}),
            "voice_settings": {
                "stability": float(char_settings.get("stability", 0.7)),
                "similarity_boost": float(char_settings.get("similarity_boost", 0.85)),
                "style": float(char_settings.get("style", 0.6)),
                "speed": float(speed_clamped),
                "pitch": float(pitch_clamped),
            },
            "output_format": "pcm_44100",
        }
        
        # Try each model until one succeeds
        last_error = None
        for model in models_to_try:
            try:
                print(f"🎯 Trying FAL.ai TTS model: {model}")
                print(f"   Speed: {speed_clamped:.2f}, Pitch: {pitch_clamped:.2f}")
                if voice_name_or_id:
                    print(f"   Voice: {voice_name_or_id}")
                
                # Adjust arguments based on model
                arguments = base_arguments.copy()
                if "minimax" in model:
                    # MiniMax may have different parameter structure
                    arguments.pop("voice_settings", None)  # Remove if not supported
                    if voice_name_or_id:
                        arguments["voice_id"] = voice_name_or_id
                else:
                    # For ElevenLabs models, try both voice name and voice_id
                    # Some voices work with name (Rachel), others need ID
                    if voice_name_or_id and len(voice_name_or_id) > 20:  # Likely a voice_id
                        arguments["voice_id"] = voice_name_or_id
                        arguments.pop("voice", None)  # Remove voice if using voice_id
                    # If voice_name_or_id is short (like "Rachel"), keep "voice" parameter
                
                submit_result = fal_client.submit(model, arguments=arguments)
                
                # Some SDK versions require polling .get(), others return dict directly
                try:
                    result = submit_result.get()
                except AttributeError:
                    result = submit_result
                
                # Locate audio URL (result schema can vary)
                audio_url = None
                if isinstance(result, dict):
                    # Known shapes: {"audio": {"url": ...}} or {"audio": "https://...mp3"} or {"audio_url": "..."} or {"output": "..."}
                    audio = result.get("audio")
                    if isinstance(audio, dict):
                        audio_url = audio.get("url")
                    elif isinstance(audio, str):
                        audio_url = audio
                    if not audio_url:
                        audio_url = result.get("audio_url") or result.get("output") or result.get("url")
                if not audio_url:
                    print(f"⚠️ Model {model} returned no audio URL, trying next model...")
                    last_error = f"No audio URL from {model}"
                    continue
                
                # Download audio and convert to WAV (if not already WAV)
                async with httpx.AsyncClient() as client:
                    resp = await client.get(audio_url, timeout=60.0)
                    resp.raise_for_status()
                    mp3_bytes = resp.content
                    if not mp3_bytes or len(mp3_bytes) < 100:
                        print(f"⚠️ Model {model} audio too small, trying next model...")
                        last_error = f"Audio too small from {model}"
                        continue
                
                try:
                    wav_bytes = await convert_mp3_to_wav(mp3_bytes)
                    print(f"✅ FAL.ai TTS MP3→WAV ({model}): {len(wav_bytes)} bytes")
                    return wav_bytes
                except FileNotFoundError:
                    print("⚠️ FFmpeg not found, returning MP3 bytes")
                    return mp3_bytes
                except Exception as e:
                    print(f"⚠️ MP3→WAV conversion failed: {e}, returning MP3")
                    return mp3_bytes
                    
            except Exception as e:
                print(f"⚠️ Model {model} failed: {e}, trying next model...")
                last_error = str(e)
                continue
        
        # All models failed
        print(f"❌ All FAL.ai TTS models failed. Last error: {last_error}")
        return None
    except Exception as e:
        print(f"❌ FAL.ai TTS failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def _generate_tts_direct_elevenlabs(text: str, voice_id: str, char_settings: dict, speed: float = 1.0, pitch: float = 1.0) -> bytes:
    """Direct ElevenLabs API call (preferred method for reliable voice_id usage)"""
    try:
        elevenlabs_key = settings.ELEVENLABS_API_KEY.strip() if settings.ELEVENLABS_API_KEY else None
        if not elevenlabs_key:
            print("❌ ELEVENLABS_API_KEY not found")
            return None
            
        import httpx
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        
        speed_clamped = max(0.5, min(1.5, speed))
        pitch_clamped = max(0.5, min(1.5, pitch))
        
        # ElevenLabs API: speed and pitch are in voice_settings
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",  # Use multilingual for better language support
            "voice_settings": {
                "stability": char_settings["stability"],
                "similarity_boost": char_settings["similarity_boost"],
                "style": char_settings["style"],
                "use_speaker_boost": True,
                "speed": speed_clamped,
                "pitch": pitch_clamped,
            }
        }
        
        print(f"🎯 Direct ElevenLabs API:")
        print(f"   Voice ID: {voice_id}")
        print(f"   Speed: {speed_clamped:.2f}")
        print(f"   Pitch: {pitch_clamped:.2f}")
        print(f"   Stability: {char_settings['stability']:.2f}")
        print(f"   Style: {char_settings['style']:.2f}")
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": elevenlabs_key
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=30.0)
            
            # Check response status
            if response.status_code != 200:
                # Try to get error message from response
                try:
                    error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else None
                    error_msg = error_data.get("detail", {}).get("message", str(error_data))
                except:
                    error_msg = response.text[:500] if hasattr(response, 'text') and response.text else "No error details"
                
                print(f"❌ ElevenLabs API returned status {response.status_code}")
                if error_msg:
                    print(f"   Error: {error_msg}")
                    # Check for quota exceeded error
                    if "quota" in error_msg.lower() or "credits" in error_msg.lower():
                        print(f"   ⚠️  QUOTA EXCEEDED - Please add credits to your ElevenLabs account")
                        print(f"   ⚠️  Script will continue but audio generation will fail until quota is restored")
                print(f"   URL: {url}")
                print(f"   Voice ID: {voice_id}")
                return None
            
            audio_bytes = response.content
            
            # Check if response is actually an error message (JSON) instead of audio
            if len(audio_bytes) < 100:
                # Try to parse as JSON to see if it's an error
                try:
                    import json
                    error_data = json.loads(audio_bytes.decode('utf-8'))
                    error_msg = error_data.get("detail", {}).get("message", str(error_data))
                    if error_msg:
                        print(f"❌ ElevenLabs API returned error in response body: {error_msg}")
                        if "quota" in error_msg.lower() or "credits" in error_msg.lower():
                            print(f"   ⚠️  QUOTA EXCEEDED - Please add credits to your ElevenLabs account")
                            print(f"   ⚠️  Script will continue but audio generation will fail until quota is restored")
                        return None
                except:
                    pass
                
                print(f"❌ ElevenLabs API returned empty or too small audio: {len(audio_bytes) if audio_bytes else 0} bytes")
                print(f"   Response headers: {dict(response.headers)}")
                return None
            
            print(f"✅ Generated audio (MP3): {len(audio_bytes)} bytes")
            
            # Convert MP3 to WAV (iOS prefers WAV format)
            try:
                audio_bytes = await convert_mp3_to_wav(audio_bytes)
                print(f"✅ Converted MP3 to WAV: {len(audio_bytes)} bytes")
            except FileNotFoundError:
                # FFmpeg not installed - return MP3 as-is
                print(f"⚠️ FFmpeg not found, returning MP3 (iOS AVPlayer supports MP3)")
            except Exception as e:
                print(f"⚠️ MP3 to WAV conversion failed: {e}, returning MP3")
            
            return audio_bytes
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            print(f"❌ ElevenLabs API returned 401 Unauthorized - API key may be invalid or expired")
            print(f"   Please check your ELEVENLABS_API_KEY in .env file")
            if hasattr(e.response, 'text'):
                print(f"   Error details: {e.response.text[:500]}")
            return None
        elif e.response.status_code == 422:
            error_text = e.response.text[:500] if hasattr(e.response, 'text') else "Validation error"
            print(f"❌ ElevenLabs API returned 422 Validation Error: {error_text}")
            return None
        else:
            error_text = e.response.text[:500] if hasattr(e.response, 'text') else str(e)
            print(f"❌ Direct ElevenLabs API failed with status {e.response.status_code}: {error_text}")
            import traceback
            traceback.print_exc()
            return None
    except httpx.TimeoutException as e:
        print(f"❌ ElevenLabs API request timed out: {e}")
        return None
    except Exception as e:
        print(f"❌ Direct ElevenLabs API failed: {e}")
        import traceback
        traceback.print_exc()
        return None

# Silent audio generation is now in utils.audio_generator
create_minimal_silent_mp3 = generate_silent_audio  # Alias for backward compatibility

# Initialize FastAPI app
app = FastAPI(title="Mino Backend API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# Firebase and FAL client are initialized via config modules above
# Import fal_client for TTS generation
try:
    import fal_client
    if settings.FAL_API_KEY:
        os.environ['FAL_KEY'] = settings.FAL_API_KEY
        print("✅ FAL.ai client initialized")
    else:
        fal_client = None
except ImportError:
    print("⚠️ fal-client not installed, FAL.ai features disabled")
    fal_client = None

# Firebase Auth verification
async def verify_firebase_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Verify Firebase Auth token and return user ID"""
    return await firebase_config.verify_token(authorization)

# Import models
from models import (
    BadgeUnlockedRequest, BadgeUnlockedResponse,
    StreakUpdatedRequest, StreakUpdatedResponse,
    TTSRequest, TTSResponse,
    LLMRequest, LLMResponse,
    ComposeRequest, ComposeResponse,
    ReceiptRequest, ReceiptResponse,
    VideoGenerationRequest, VideoGenerationResponse,
    ComposeStoryRequest, ComposeStoryResponse,
    StoryCompletedRequest, StoryCompletedResponse,
    DeviceRegistrationRequest, DeviceRegistrationResponse,
    BadgeUnlockedRequest, BadgeUnlockedResponse,
    StreakUpdatedRequest, StreakUpdatedResponse
)
from services.story_composer import (
    to_character_slug,
    content_story_path,
    generate_story_with_openai,
)
from services.push_notification_service import get_push_notification_service
from services.notification_scheduler import schedule_delayed_notification

# Use CHARACTER_VOICES from settings (alias for backward compatibility)
CHARACTER_VOICES = settings.CHARACTER_VOICES

# TTS Service with idempotent Storage caching
async def generate_tts(text: str, style: dict, lang: str, character: str = None, topic: str = None, scene_index: int = None) -> str:
    """Generate (or reuse) TTS audio and return a public URL.

    Strategy:
      - For pre-generated content: use character/topic/scene-based key
      - For dynamic content without scene refs: return mock/silent URL (no legacy save)
      - If existing file exists -> return its URL
    """
    character_normalized = character.lower() if character else None
    text = clean_text_for_tts(text, character_normalized)
    
    # Topic mapping: Map StorySelectionView topic names to actual file names
    # This aligns with how stories are generated and stored (same as ContentLoader.swift)
    topic_mapping = {
        "sleep": "bedtime",                    # sleep → bedtime.json
        "sibling issues": ["sibling_issues", "sibling"],  # sibling issues → try sibling_issues.json first, then sibling.json
        "sibling": ["sibling", "sibling_issues"],        # sibling → try sibling.json first, then sibling_issues.json (fallback)
        "screen time": "screen_time",          # screen time → screen_time.json
        "digital safety": "digital_safety",    # digital safety → digital_safety.json
        "feeling sad": "feeling_sad",          # feeling sad → feeling_sad.json
        "emotional regulation": "emotional_regulation",  # emotional regulation → emotional_regulation.json
        "behavior attention": "behavior_attention",       # behavior attention → behavior_attention.json
        "body parts": "body_parts",            # body parts → body_parts.json
        "fairy tales": "fairy_tales",         # fairy tales → fairy_tales.json
        "food": "nutrition",                   # food → nutrition.json (backend file name)
        "transitions_change": "transitions",   # transitions_change → transitions (story ID variant from rules.json)
        "transitions_attention": "transitions", # transitions_attention → transitions (story ID variant)
    }
    
    # Map topic to actual file name (same logic as ContentLoader)
    topic_normalized = topic.lower() if topic else None
    topic_mapped = topic_mapping.get(topic_normalized, topic_normalized) if topic_normalized else None
    
    # Handle list of candidates (try first, then fallback)
    if isinstance(topic_mapped, list):
        topic_file = topic_mapped[0]  # Use first candidate
    else:
        topic_file = topic_mapped
    
    print(f"🔊 [TTS] Generating audio: character={character_normalized}, topic={topic_normalized} → {topic_file}, lang={lang}, scene_index={scene_index}")

    if character_normalized and topic_file is not None and scene_index is not None:
        key = f"{character_normalized}_{topic_file}_{scene_index}"
        # Language-specific audio path: {character}/{lang}/{topic}_{scene_index}.wav
        character_dir = AUDIO_BASE_DIR / character_normalized / lang
        audio_filename = f"{topic_file}_{scene_index}.wav"
        local_audio_path = character_dir / audio_filename
        if local_audio_path.exists() and local_audio_path.stat().st_size > 0:
            print(f"✅ [TTS] Using existing audio: {audio_filename} (lang={lang})")
            return f"http://127.0.0.1:8000/local-audio/{key}.wav?lang={lang}"
    else:
        # No scene context → do not write legacy files; return mock
        return f"http://127.0.0.1:8000/mock-audio/{hashlib.sha256(text.encode()).hexdigest()}.wav"

    # Generate via ElevenLabs (FAL)
    # Get character voice settings - try exact match, then case-insensitive, then default
    character_voice_key = character_normalized or "mino"
    char_voice_config = settings.CHARACTER_VOICES.get(character_voice_key)
    if not char_voice_config:
        # Try case-insensitive match
        for key, value in settings.CHARACTER_VOICES.items():
            if key.lower() == character_voice_key.lower():
                char_voice_config = value
                break
    
    # Use character voice settings (matching original character inspiration) or fallback to style/defaults
    if char_voice_config:
        emotion = style.get("emotion", char_voice_config.get("emotion", "happy"))
        speed = style.get("speed", char_voice_config.get("speed", 1.0))
        pitch = style.get("pitch", char_voice_config.get("pitch", 1.0))
    else:
        emotion = style.get("emotion", "happy")
        speed = style.get("speed", 1.0)
        pitch = style.get("pitch", 1.0)
    
    # Generate TTS with language support (ElevenLabs multilingual model auto-detects, but we log it)
    print(f"🌍 [TTS] Generating TTS for language: {lang}, text preview: {text[:50]}...")
    audio_bytes = await generate_tts_with_elevenlabs(text, character_voice_key, emotion, speed, pitch, topic_file or topic)

    if audio_bytes and len(audio_bytes) > 100:
        is_mp3 = audio_bytes[:3] == b'ID3' or audio_bytes[:2] == b'\xff\xfb'
        audio_ext = '.mp3' if is_mp3 else '.wav'
        try:
            # Language-specific audio path: {character}/{lang}/{topic}_{scene_index}.ext
            character_dir = AUDIO_BASE_DIR / character_normalized / lang
            character_dir.mkdir(parents=True, exist_ok=True)
            # Use topic_file (mapped) for filename to match ContentLoader mapping
            audio_filename = f"{topic_file}_{scene_index}{audio_ext}" if topic_file else f"{topic}_{scene_index}{audio_ext}"
            audio_path = character_dir / audio_filename
            with open(audio_path, 'wb') as f:
                f.write(audio_bytes)
            key = f"{character_normalized}_{topic_file}_{scene_index}" if topic_file else f"{character_normalized}_{topic}_{scene_index}"
            print(f"✅ [TTS] Saved audio: {audio_filename} (lang={lang}, character={character_normalized}, path={character_dir})")
            return f"http://127.0.0.1:8000/local-audio/{key}{audio_ext}?lang={lang}"
        except Exception as e:
            print(f"❌ Local storage failed: {e}")
            return f"http://127.0.0.1:8000/mock-audio/{character_normalized}_{topic}_{scene_index}.wav"
    else:
        return f"http://127.0.0.1:8000/mock-audio/{character_normalized}_{topic}_{scene_index}.wav"

# LLM Service
async def generate_llm_response(template: str, vars: dict) -> str:
    """Generate LLM response using OpenAI"""
    try:
        import openai
        
        # Format the template with variables
        formatted_template = template
        for key, value in vars.items():
            formatted_template = formatted_template.replace(f"{{{{{key}}}}}", str(value))
        
        # Call OpenAI API
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are Mino, a friendly character for children aged 5-9."},
                {"role": "user", "content": formatted_template}
            ],
            max_tokens=50,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"LLM generation failed: {e}")
        return "Hello! How are you today?"

# Video Composition using fal.ai
async def compose_video(base_video_uri: str, audio_url: str, session_id: str, user_id: str) -> str:
    """Compose video with audio using fal.ai mmaudio-v2 or ffmpeg fallback"""
    try:
        # Try fal.ai first if API key and client are available
        if settings.FAL_API_KEY and fal_client:
            try:
                result = fal_client.submit(
                    "fal-ai/mmaudio-v2",
                    arguments={
                        "video_url": base_video_uri,
                        "audio_url": audio_url,
                        "prompt": "Sync the audio with the video character's mouth movements"
                    }
                )
                
                video_url = result.get("video_url", "")
                if video_url:
                    # Download and upload to Firebase Storage
                    async with httpx.AsyncClient() as client:
                        response = await client.get(video_url)
                        video_data = response.content
                    
                    return await upload_video_to_storage(video_data, session_id, user_id)
            except Exception as e:
                print(f"fal.ai composition failed, using ffmpeg fallback: {e}")
        
        # Fallback: Use ffmpeg to compose (if base_video_uri is a local file)
        # For now, return a placeholder URL
        print("⚠️ Video composition using placeholder - implement ffmpeg compose if needed")
        return f"https://your-storage-bucket.com/video/{uuid.uuid4()}.mp4"
        
    except Exception as e:
        print(f"❌ Video composition failed: {e}")
        return f"https://your-storage-bucket.com/video/fallback.mp4"

async def upload_video_to_storage(video_data: bytes, session_id: str, user_id: str) -> str:
    """Upload video to Firebase Storage and return public URL"""
    if not bucket:
        print("⚠️ Firebase Storage not available")
        return f"https://your-storage-bucket.com/video/{uuid.uuid4()}.mp4"
    
    try:
        blob_name = f"sessions/{session_id}/{user_id}/{uuid.uuid4()}.mp4"
        blob = bucket.blob(blob_name)
        blob.upload_from_string(video_data, content_type='video/mp4')
        
        # Make the blob publicly accessible
        blob.make_public()
        
        print(f"✅ Video uploaded to Storage: {blob.public_url}")
        return blob.public_url
    except Exception as e:
        print(f"❌ Failed to upload video to Storage: {e}")
        return f"https://your-storage-bucket.com/video/{uuid.uuid4()}.mp4"

# API Endpoints
@app.post("/tts", response_model=TTSResponse)
async def generate_tts_endpoint(request: TTSRequest):
    """Generate TTS audio"""
    try:
        print(f"TTS request received: {request.text}")
        if request.character and request.topic is not None and request.scene_index is not None:
            print(f"Pre-generated content: {request.character}/{request.topic}/scene_{request.scene_index}")
        audio_url = await generate_tts(
            request.text, 
            request.style, 
            request.lang,
            request.character,
            request.topic,
            request.scene_index
        )
        print(f"Generated audio URL: {audio_url}")
        return TTSResponse(audioUrl=audio_url)
    except Exception as e:
        print(f"TTS endpoint error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/llm/question", response_model=LLMResponse)
async def generate_question(request: LLMRequest):
    """Generate LLM question"""
    try:
        text = await generate_llm_response(request.template, request.vars)
        return LLMResponse(text=text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/llm/followup", response_model=LLMResponse)
async def generate_followup(request: LLMRequest):
    """Generate LLM followup"""
    try:
        text = await generate_llm_response(request.template, request.vars)
        return LLMResponse(text=text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/compose", response_model=ComposeResponse)
async def compose_video_endpoint(request: ComposeRequest):
    """Compose video with audio"""
    try:
        video_url = await compose_video(
            request.base_video_uri,
            request.audio_url,
            request.session_id,
            request.user_id
        )
        return ComposeResponse(video_url=video_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/compose_story", response_model=ComposeStoryResponse)
async def compose_story_endpoint(request: ComposeStoryRequest):
    """Compose and persist a character+topic story JSON once, then reuse it.
    - Writes to: backend/storage/content/{lang}/stories/{slug}/{topic}.json
    - If file exists and overwrite=False: returns existing path (created=False)
    """
    try:
        character = request.character.strip()
        topic = request.topic.strip().lower().replace(" ", "_")
        lang = request.lang.strip().lower()
        slug = to_character_slug(character)
        out_path = content_story_path(lang, slug, topic)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        if out_path.exists() and not request.overwrite:
            return ComposeStoryResponse(path=str(out_path), created=False, story_id=f"{character.lower()}_{topic}_story")
        
        # Generate via OpenAI (or minimal fallback)
        story_data = await generate_story_with_openai(
            character,
            topic,
            lang,
            duration_minutes=request.durationMinutes
        )
        
        # Validate minimal schema
        if not story_data or "scenes" not in story_data or not isinstance(story_data["scenes"], list):
            raise HTTPException(status_code=500, detail="Invalid story data from LLM")
        
        # Inject durationMinutes if provided and missing
        if request.durationMinutes is not None and "durationMinutes" not in story_data:
            story_data["durationMinutes"] = request.durationMinutes

        # Persist
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(story_data, f, ensure_ascii=False, indent=2)
        
        return ComposeStoryResponse(path=str(out_path), created=True, story_id=story_data.get("id", f"{character.lower()}_{topic}_story"))
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ compose_story error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/story/{character}/{topic}")
async def serve_story(character: str, topic: str, lang: str = "en"):
    """Serve story JSON file from backend storage.
    
    Path format: backend/storage/content/{lang}/stories/{character}/{topic}.json
    Topic mapping: Maps iOS topic names to actual file names (same as audio serving)
    """
    try:
        from services.story_composer import content_story_path
        
        # Topic mapping: Map iOS topic names to actual file names (same as audio serving)
        topic_mapping = {
            "sleep": "bedtime",
            "sibling issues": "sibling_issues",
            "sibling": "sibling_issues",
            "screen time": "screen_time",
            "digital safety": "digital_safety",
            "feeling sad": "feeling_sad",
            "emotional regulation": "emotional_regulation",
            "behavior attention": "behavior_attention",
            "body parts": "body_parts",
            "fairy tales": "fairy_tales",
            "food": "nutrition",
            "transitions_change": "transitions",
            "transitions_attention": "transitions",
        }
        
        topic_normalized = topic.lower()
        topic_file = topic_mapping.get(topic_normalized, topic_normalized)
        
        # Try mapped topic first, then original topic
        topic_candidates = [topic_file]
        if topic_file != topic_normalized:
            topic_candidates.append(topic_normalized)
        
        print(f"🔍 [serve_story] Requested: character={character}, topic={topic} (normalized: {topic_normalized}, mapped: {topic_file}), lang={lang}")
        print(f"   Topic candidates: {topic_candidates}")
        
        # Try each candidate
        for topic_candidate in topic_candidates:
            story_path = content_story_path(lang, character.lower(), topic_candidate)
            if story_path.exists() and story_path.stat().st_size > 0:
                print(f"✅ [serve_story] Serving: {story_path} (lang={lang}, size: {story_path.stat().st_size} bytes)")
                return FileResponse(str(story_path), media_type="application/json")
        
        # Fallback: Try to find any story for this character in the requested language
        print(f"🔄 [serve_story] Specific topic story not found, trying to find any story for {character} in {lang}...")
        character_stories_dir = story_path.parent  # content_story_path returns path with filename, so parent is the character directory
        if character_stories_dir.exists():
            try:
                # List all JSON files in the character directory
                for story_file in character_stories_dir.glob("*.json"):
                    if story_file.exists() and story_file.stat().st_size > 0:
                        print(f"✅ [serve_story] Serving (any available story): {story_file} (lang={lang}, size: {story_file.stat().st_size} bytes)")
                        return FileResponse(str(story_file), media_type="application/json")
            except Exception as e:
                print(f"⚠️ [serve_story] Error scanning directory: {e}")
        
        print(f"⚠️ [serve_story] Story not found: character={character}, topic={topic} (normalized: {topic_normalized}, mapped: {topic_file}), lang={lang}")
        raise HTTPException(status_code=404, detail=f"Story not found for character={character}, topic={topic}, lang={lang}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [serve_story] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/local-audio/{audio_id}")
async def serve_local_audio(audio_id: str, lang: str = "en"):
    """Serve locally stored character-based audio files only.

    Path format: backend/storage/characters/{character}/{lang}/{topic}_{scene_index}.{ext}
    Language-specific: Each language has its own subdirectory
    Supports both .wav and .mp3 extensions.
    
    Topic mapping: Maps iOS topic names to actual file names (same as generate_tts)
    """
    try:
        audio_id_clean = audio_id.replace('.wav', '').replace('.mp3', '')
        parts = audio_id_clean.split('_')
        if len(parts) >= 3:
            character = parts[0]
            # Last part is always scene_index (number), rest is topic
            # Example: "spongebob_transitions_change_0" -> character="spongebob", topic="transitions_change", scene_index="0"
            scene_index = parts[-1]  # Last part is scene_index
            topic = '_'.join(parts[1:-1])  # Everything between character and scene_index is topic
            
            # Topic mapping: Map iOS topic names to actual file names (same as generate_tts)
            # This ensures sleep → bedtime mapping is used for file lookup
            topic_mapping = {
                "sleep": "bedtime",                    # sleep → bedtime.json
                "sibling issues": "sibling_issues",    # sibling issues → sibling_issues.json
                "screen time": "screen_time",          # screen time → screen_time.json
                "digital safety": "digital_safety",    # digital safety → digital_safety.json
                "feeling sad": "feeling_sad",          # feeling sad → feeling_sad.json
                "emotional regulation": "emotional_regulation",  # emotional regulation → emotional_regulation.json
                "behavior attention": "behavior_attention",       # behavior attention → behavior_attention.json
                "body parts": "body_parts",            # body parts → body_parts.json
                "fairy tales": "fairy_tales",         # fairy tales → fairy_tales.json
                "food": "nutrition",                   # food → nutrition.json (backend file name)
                "transitions_change": "transitions",   # transitions_change → transitions (story ID variant)
                "transitions_attention": "transitions", # transitions_attention → transitions (story ID variant)
            }
            
            # Map topic to actual file name (same logic as generate_tts and ContentLoader)
            topic_normalized = topic.lower()
            topic_file = topic_mapping.get(topic_normalized, topic_normalized)
            
            # Try mapped topic first, then original topic, then try without mapping
            topic_candidates = [topic_file]
            if topic_file != topic_normalized:
                topic_candidates.append(topic_normalized)  # Also try original as fallback
            
            # Also try topic without underscores (for cases like "transitions_change" -> "transitionschange")
            topic_no_underscore = topic_normalized.replace('_', '')
            if topic_no_underscore not in topic_candidates:
                topic_candidates.append(topic_no_underscore)
            
            print(f"🔍 [serve_local_audio] Parsed: character={character}, topic={topic} (normalized: {topic_normalized}), scene_index={scene_index}, lang={lang}")
            print(f"   Topic candidates: {topic_candidates}")
            
            # Language-specific path: {character}/{lang}/{topic}_{scene_index}.ext
            for topic_candidate in topic_candidates:
                for ext in ['.wav', '.mp3']:
                    character_path = AUDIO_BASE_DIR / character.lower() / lang / f"{topic_candidate}_{scene_index}{ext}"
                    if character_path.exists() and character_path.stat().st_size > 0:
                        media_type = "audio/mpeg" if ext == '.mp3' else "audio/wav"
                        print(f"✅ [serve_local_audio] Serving: {character_path} (lang={lang}, size: {character_path.stat().st_size} bytes, type: {media_type})")
                        return FileResponse(str(character_path), media_type=media_type)
            
            # Fallback: Try old path structure (for backward compatibility)
            for topic_candidate in topic_candidates:
                for ext in ['.wav', '.mp3']:
                    legacy_path = AUDIO_BASE_DIR / character.lower() / f"{topic_candidate}_{scene_index}{ext}"
                    if legacy_path.exists() and legacy_path.stat().st_size > 0:
                        media_type = "audio/mpeg" if ext == '.mp3' else "audio/wav"
                        print(f"⚠️ [serve_local_audio] Using legacy path (no lang): {legacy_path}")
                        return FileResponse(str(legacy_path), media_type=media_type)
            
            # Fallback: Try to find any audio file for this character in the requested language
            # If specific topic audio not found, try to find any audio file for this character
            print(f"🔄 [serve_local_audio] Specific topic audio not found, trying to find any audio for {character} in {lang}...")
            character_lang_dir = AUDIO_BASE_DIR / character.lower() / lang
            if character_lang_dir.exists():
                # Try to find any audio file with the same scene_index
                for ext in ['.wav', '.mp3']:
                    # List all files in the directory
                    try:
                        for audio_file in character_lang_dir.glob(f"*_{scene_index}{ext}"):
                            if audio_file.exists() and audio_file.stat().st_size > 0:
                                media_type = "audio/mpeg" if ext == '.mp3' else "audio/wav"
                                print(f"✅ [serve_local_audio] Serving (any available audio): {audio_file} (lang={lang}, size: {audio_file.stat().st_size} bytes, type: {media_type})")
                                return FileResponse(str(audio_file), media_type=media_type)
                    except Exception as e:
                        print(f"⚠️ [serve_local_audio] Error scanning directory: {e}")
            
            # Collect all tried paths for better error reporting
            tried_paths = []
            for topic_candidate in topic_candidates:
                for ext in ['.wav', '.mp3']:
                    tried_paths.append(str(AUDIO_BASE_DIR / character.lower() / lang / f"{topic_candidate}_{scene_index}{ext}"))
                    tried_paths.append(str(AUDIO_BASE_DIR / character.lower() / f"{topic_candidate}_{scene_index}{ext}"))  # Legacy paths
                    if lang != "en":
                        tried_paths.append(str(AUDIO_BASE_DIR / character.lower() / "en" / f"{topic_candidate}_{scene_index}{ext}"))  # EN fallback
            
            print(f"⚠️ [serve_local_audio] File not found: character={character}, topic={topic} (normalized: {topic_normalized}, mapped: {topic_file}), scene_index={scene_index}, lang={lang}")
            print(f"   Tried {len(tried_paths)} paths:")
            for path in tried_paths:
                exists = Path(path).exists()
                print(f"      {'✅' if exists else '❌'} {path} {'(exists)' if exists else '(not found)'}")
        return await mock_audio(audio_id)
    except Exception as e:
        print(f"❌ [serve_local_audio] Error: {e}")
        import traceback
        traceback.print_exc()
        return await mock_audio(audio_id)

@app.get("/mock-audio/{audio_id}")
async def mock_audio(audio_id: str):
    """Serve audio files using fal.ai TTS when Firebase is not configured."""
    try:
        # Extract text from audio_id (for now, use a default Mino greeting)
        mino_text = "Hello! I'm Mino, your colorful space friend! 🌈"
        
        # Generate TTS with ElevenLabs using Mino's voice
        audio_bytes = await generate_tts_with_elevenlabs(
            text=mino_text,
            voice="gender-neutral-mid",  # Mino's voice
            emotion="happy",
            speed=1.0,
            pitch=1.1
        )
        
        if audio_bytes:
            print(f"Generated fal.ai audio for: {mino_text}")
            return Response(content=audio_bytes, media_type="audio/wav")
        else:
            print("fal.ai failed, using silent fallback")
            # Fallback to silent audio
            audio_bytes = create_minimal_silent_mp3(3.0)
            return Response(content=audio_bytes, media_type="audio/wav")
            
    except Exception as e:
        print(f"Mock audio generation failed: {e}")
        # Fallback to silent audio
        audio_bytes = create_minimal_silent_mp3(3.0)
        return Response(content=audio_bytes, media_type="audio/wav")

@app.post("/iap/verify", response_model=ReceiptResponse)
async def verify_receipt(request: ReceiptRequest):
    """Verify App Store receipt with Apple's servers.
    
    Best Practice: Always verify receipts on your backend server, not on the client.
    This prevents receipt tampering and ensures security.
    
    Production Flow (Recommended):
    1. Always try PRODUCTION first: https://buy.itunes.apple.com/verifyReceipt
    2. If status 21007 (sandbox receipt sent to production), then try sandbox
    3. This ensures production receipts are verified correctly
    
    Important:
    - Production receipts MUST be verified with production URL
    - Sandbox receipts will return status 21007 when sent to production
    - Backend automatically handles both production and sandbox receipts
    - StoreKit 2 automatically uses production for real purchases
    """
    try:
        settings = get_settings()
        
        if not settings.APP_STORE_SHARED_SECRET:
            print("⚠️ APP_STORE_SHARED_SECRET not configured, using mock verification")
            # Fallback for development
            return ReceiptResponse(
                valid=True,
                status=0,
                environment="Sandbox",
                message="Mock verification (APP_STORE_SHARED_SECRET not set)"
            )
        
        # Prepare request body for Apple
        verify_data = {
            "receipt-data": request.receipt_data,
            "password": settings.APP_STORE_SHARED_SECRET,
            "exclude-old-transactions": True  # Only return latest transaction
        }
        
        # Try production first
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    settings.APP_STORE_VERIFY_RECEIPT_PRODUCTION,
                    json=verify_data
                )
                response.raise_for_status()
                apple_response = response.json()
                
                status = apple_response.get("status", -1)
                
                # Status 21007 means receipt is from sandbox, try sandbox URL
                if status == 21007:
                    print("🔄 Receipt is from sandbox, verifying with sandbox URL")
                    response = await client.post(
                        settings.APP_STORE_VERIFY_RECEIPT_SANDBOX,
                        json=verify_data
                    )
                    response.raise_for_status()
                    apple_response = response.json()
                    status = apple_response.get("status", -1)
                    environment = "Sandbox"
                else:
                    environment = "Production"
                
                # Status 0 = valid receipt
                if status == 0:
                    receipt_info = apple_response.get("receipt", {})
                    latest_receipt_info = apple_response.get("latest_receipt_info", [])
                    
                    # Get latest transaction
                    if latest_receipt_info:
                        latest_transaction = latest_receipt_info[-1]
                        
                        expires_date_ms = None
                        trial_end_date_ms = None
                        is_trial_period = latest_transaction.get("is_trial_period", "false") == "true"
                        is_in_intro_offer_period = latest_transaction.get("is_in_intro_offer_period", "false") == "true"
                        product_id = latest_transaction.get("product_id", "")
                        
                        # Parse expiration date
                        if "expires_date_ms" in latest_transaction:
                            expires_date_ms = int(latest_transaction["expires_date_ms"])
                        
                        # Parse trial end date
                        if "expires_date" in latest_transaction and is_trial_period:
                            # Try to parse expires_date (can be in different formats)
                            try:
                                if isinstance(latest_transaction["expires_date"], str):
                                    # ISO format or timestamp string
                                    trial_end_date_ms = int(latest_transaction.get("expires_date_ms", 0))
                                else:
                                    trial_end_date_ms = int(latest_transaction.get("expires_date_ms", 0))
                            except:
                                trial_end_date_ms = expires_date_ms
                        
                        print(f"✅ Receipt verified: product={product_id}, expires={expires_date_ms}, trial={is_trial_period}")
                        
                        # Store subscription status in Firestore if user_id provided
                        if request.user_id and db:
                            try:
                                user_ref = db.collection("subscriptions").document(request.user_id)
                                user_ref.set({
                                    "user_id": request.user_id,
                                    "product_id": product_id,
                                    "expires_date_ms": expires_date_ms,
                                    "trial_end_date_ms": trial_end_date_ms,
                                    "is_trial_period": is_trial_period,
                                    "is_in_intro_offer_period": is_in_intro_offer_period,
                                    "environment": environment,
                                    "verified_at": firestore.SERVER_TIMESTAMP,
                                    "updated_at": firestore.SERVER_TIMESTAMP
                                }, merge=True)
                                print(f"✅ Subscription status saved to Firestore for user: {request.user_id}")
                            except Exception as e:
                                print(f"⚠️ Failed to save subscription to Firestore: {e}")
                        
                        return ReceiptResponse(
                            valid=True,
                            status=status,
                            environment=environment,
                            expires_date_ms=expires_date_ms,
                            trial_end_date_ms=trial_end_date_ms,
                            is_trial_period=is_trial_period,
                            is_in_intro_offer_period=is_in_intro_offer_period,
                            product_id=product_id,
                            message="Receipt verified successfully"
                        )
                    else:
                        return ReceiptResponse(
                            valid=False,
                            status=status,
                            environment=environment,
                            message="No active subscription found in receipt"
                        )
                else:
                    # Invalid receipt
                    error_messages = {
                        21000: "The App Store could not read the JSON object you provided.",
                        21002: "The data in the receipt-data property was malformed or missing.",
                        21003: "The receipt could not be authenticated.",
                        21004: "The shared secret you provided does not match the shared secret on file.",
                        21005: "The receipt server is not currently available.",
                        21006: "This receipt is valid but the subscription has expired.",
                        21007: "This receipt is from the test environment, but it was sent to the production environment for verification.",
                        21008: "This receipt is from the production environment, but it was sent to the test environment for verification.",
                        21010: "This receipt could not be authorized."
                    }
                    
                    error_message = error_messages.get(status, f"Unknown error (status: {status})")
                    print(f"❌ Receipt verification failed: {error_message}")
                    
                    return ReceiptResponse(
                        valid=False,
                        status=status,
                        message=error_message
                    )
                    
            except httpx.HTTPError as e:
                print(f"❌ HTTP error verifying receipt: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to verify receipt: {str(e)}")
                
    except Exception as e:
        print(f"❌ Receipt verification error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/summary")
async def generate_summary(session_data: dict, user_id: Optional[str] = Depends(verify_firebase_token)):
    """Save session summary to Firestore"""
    try:
        # Store session data in Firestore
        if db:
            session_id = session_data.get('session_id', str(uuid.uuid4()))
            doc_ref = db.collection('sessions').document(session_id)
            
            # Add metadata
            session_data['saved_at'] = firestore.SERVER_TIMESTAMP
            session_data['user_id'] = user_id or session_data.get('user_id', 'anonymous')
            
            doc_ref.set(session_data, merge=True)
            print(f"✅ Session saved to Firestore: {session_id}")
        
        return {"status": "success", "message": "Session saved", "session_id": session_data.get('session_id')}
    except Exception as e:
        print(f"❌ Failed to save session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-video")
async def generate_video_endpoint(request: VideoGenerationRequest):
    """Generate character video using FAL.ai (bütçe dostu)"""
    try:
        from utils.video_generator import generate_character_video
        from pathlib import Path
        
        # Determine output directory
        project_root = Path(__file__).parent.parent
        output_dir = project_root / "mino" / "Assets" / "characters" / request.character_name.lower()
        
        video_path = await generate_character_video(
            character_name=request.character_name.lower(),
            action=request.action.lower(),
            profile_image_path=request.profile_image_path,
            output_dir=output_dir
        )
        
        if video_path:
            return VideoGenerationResponse(
                video_path=video_path,
                success=True,
                message=f"Video generated: {video_path}"
            )
        else:
            return VideoGenerationResponse(
                success=False,
                message="Failed to generate video"
            )
    except Exception as e:
        print(f"❌ Video generation endpoint error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "mino-backend"}

# Characters and topics are managed from rules.json in UI - no backend endpoints needed
# Backend only handles: TTS generation, video composition, LLM interactions
# Custom story generation (for Pro feature) uses backend LLM

@app.post("/generate-custom-story")
async def generate_custom_story(request: dict):
    """Generate a custom story based on parent's input"""
    try:
        character = request.get("character", "Mino")
        topic = request.get("topic", "")
        content = request.get("content", "")
        lang = request.get("lang", "en")
        
        if not content or not topic:
            raise HTTPException(status_code=400, detail="Topic and content are required")
        
        print(f"📖 Generating custom story for {character}/{topic} (lang: {lang})")
        
        if not settings.OPENAI_API_KEY:
            # Fallback: Return a basic story structure
            return {
                "id": f"custom_{character.lower()}_{topic.lower()}_{int(time.time())}",
                "title": f"{character}'s Custom {topic.title()} Story",
                "character": character,
                "topic": topic,
                "scenes": [
                    {
                        "id": "opening",
                        "type": "opening",
                        "text": f"{character}: Hello! Let me tell you a special story about {topic}!",
                        "videoKey": "idle"
                    },
                    {
                        "id": "scene_1",
                        "type": "instruction",
                        "text": content,
                        "videoKey": "speak"
                    },
                    {
                        "id": "closure",
                        "type": "closure",
                        "text": f"{character}: I hope you enjoyed our story about {topic}!",
                        "videoKey": "wave"
                    }
                ]
            }
        
        # Generate story using LLM
        import openai
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        
        prompt = f"""You are {character}, a friendly character talking to a child aged 5-9.
The parent wants a story about: {topic}

Parent's story request/details: {content}

Create an engaging, age-appropriate story with 5-7 scenes. Each scene should be engaging, positive, and suitable for children.
Format as JSON with this structure:
{{
  "scenes": [
    {{"id": "opening", "type": "opening", "text": "...", "videoKey": "idle"}},
    {{"id": "scene_1", "type": "question", "text": "...", "videoKey": "speak"}},
    {{"id": "scene_2", "type": "instruction", "text": "...", "videoKey": "speak"}},
    {{"id": "scene_3", "type": "listen", "text": "...", "videoKey": "listen"}},
    {{"id": "scene_4", "type": "followup", "text": "...", "videoKey": "speak"}},
    {{"id": "closure", "type": "closure", "text": "...", "videoKey": "wave"}}
  ]
}}
Only return valid JSON, no other text."""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"You are {character}, a child-friendly character. Create engaging, personalized stories based on parent requests."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.8
        )
        
        story_json_str = response.choices[0].message.content.strip()
        # Remove markdown code blocks if present
        if story_json_str.startswith("```json"):
            story_json_str = story_json_str[7:]
        if story_json_str.startswith("```"):
            story_json_str = story_json_str[3:]
        if story_json_str.endswith("```"):
            story_json_str = story_json_str[:-3]
        story_json_str = story_json_str.strip()
        
        story_data = json.loads(story_json_str)
        
        return {
            "id": f"custom_{character.lower()}_{topic.lower()}_{int(time.time())}",
            "title": f"{character}'s Custom {topic.title()} Story",
            "character": character,
            "topic": topic,
            "scenes": story_data.get("scenes", [])
        }
        
    except Exception as e:
        print(f"❌ Failed to generate custom story: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

def ensure_parent_exists(parent_id: str) -> bool:
    """Ensure parent document exists in Firestore. Creates minimal parent record if missing.
    
    Args:
        parent_id: Parent user ID (from Firebase Auth anonymous sign-in)
    
    Returns:
        True if parent exists or was created, False if Firestore unavailable
    """
    if not db:
        return False
    
    try:
        parent_ref = db.collection("parents").document(parent_id)
        parent_doc = parent_ref.get()
        
        if not parent_doc.exists:
            # Create minimal parent record (device token will be added later via register-device)
            parent_ref.set({
                "device_tokens": [],
                "notification_consent": False,
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            print(f"✅ Auto-created parent document: {parent_id}")
        return True
    except Exception as e:
        print(f"❌ Error ensuring parent exists: {e}")
        return False


@app.post("/events/story-completed", response_model=StoryCompletedResponse)
async def story_completed_endpoint(request: StoryCompletedRequest):
    """Receive story completion event and schedule parent notification.
    
    COPPA-compliant: Only stores event data, notification sent to parent only.
    """
    try:
        if not db:
            print("⚠️ Firestore not available, skipping event storage")
            return StoryCompletedResponse(
                success=False,
                message="Firestore not available"
            )
        
        # Generate event ID
        event_id = str(uuid.uuid4())
        timestamp = request.timestamp or time.time()
        
        # In this MVP, parent_id = child_id (same device, parent owns the account)
        # For future: could have separate parent-child mapping in Firestore
        parent_id = request.child_id
        
        # Ensure parent exists (auto-create if missing for anonymous users)
        ensure_parent_exists(parent_id)
        
        # Store event in Firestore (best practice: include summary for meaningful parent notes)
        event_data = {
            "child_id": request.child_id,
            "parent_id": parent_id,
            "story_id": request.story_id,
            "topic": request.topic,
            "character": request.character,
            "language": request.language,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "notified": False,
            "created_at": firestore.SERVER_TIMESTAMP
        }
        
        # Add summary if provided (best practice: meaningful note for parents)
        if request.summary:
            event_data["summary"] = request.summary
        
        event_ref = db.collection("story_events").document(event_id)
        event_ref.set(event_data)
        print(f"✅ Story completion event stored: {event_id}")
        
        # Schedule delayed notification (5 minutes)
        # This runs in background and sends notification after delay
        await schedule_delayed_notification(
            event_id=event_id,
            parent_id=parent_id,
            character=request.character,
            topic=request.topic,
            language=request.language,
            story_id=request.story_id,
            child_name=request.child_name  # Optional: will use "your child" if None
        )
        
        return StoryCompletedResponse(
            success=True,
            event_id=event_id,
            message="Event received and notification scheduled"
        )
        
    except Exception as e:
        print(f"❌ Story completion event error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/parents/register-device", response_model=DeviceRegistrationResponse)
async def register_device_endpoint(request: DeviceRegistrationRequest):
    """Register parent device token for push notifications.
    
    COPPA-compliant: Only stores device token with parent consent.
    """
    try:
        if not db:
            print("⚠️ Firestore not available, skipping device registration")
            return DeviceRegistrationResponse(
                success=False,
                message="Firestore not available"
            )
        
        # Get or create parent document
        parent_ref = db.collection("parents").document(request.parent_id)
        parent_doc = parent_ref.get()
        
        if parent_doc.exists:
            # Update existing parent document
            parent_data = parent_doc.to_dict()
            device_tokens = parent_data.get("device_tokens", [])
            
            # Add token if not already present
            if request.device_token not in device_tokens:
                device_tokens.append(request.device_token)
            
            parent_ref.update({
                "device_tokens": device_tokens,
                "notification_consent": request.notification_consent,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            print(f"✅ Updated device token for parent: {request.parent_id}")
        else:
            # Create new parent document
            parent_ref.set({
                "device_tokens": [request.device_token],
                "notification_consent": request.notification_consent,
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            print(f"✅ Created parent document with device token: {request.parent_id}")
        
        return DeviceRegistrationResponse(
            success=True,
            message="Device token registered successfully"
        )
        
    except Exception as e:
        print(f"❌ Device registration error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/events/badge-unlocked", response_model=BadgeUnlockedResponse)
async def badge_unlocked_endpoint(request: BadgeUnlockedRequest):
    """Receive badge unlock event and send notification to parent.
    
    COPPA-compliant: Notification sent to parent only.
    """
    try:
        if not db:
            print("⚠️ Firestore not available, skipping badge unlock notification")
            return BadgeUnlockedResponse(
                success=False,
                message="Firestore not available"
            )
        
        # Ensure parent exists (auto-create if missing for anonymous users)
        if not ensure_parent_exists(request.parent_id):
            return BadgeUnlockedResponse(
                success=False,
                message="Firestore not available"
            )
        
        # Get parent device tokens
        parent_ref = db.collection("parents").document(request.parent_id)
        parent_doc = parent_ref.get()
        
        if not parent_doc.exists:
            print(f"⚠️ Parent {request.parent_id} not found after ensure_parent_exists")
            return BadgeUnlockedResponse(
                success=False,
                message="Parent not found"
            )
        
        parent_data = parent_doc.to_dict()
        
        # Check consent
        if not parent_data.get("notification_consent", False):
            print(f"⚠️ Parent {request.parent_id} has not consented to notifications")
            return BadgeUnlockedResponse(
                success=False,
                message="Notification consent not given"
            )
        
        device_tokens = parent_data.get("device_tokens", [])
        if not device_tokens:
            print(f"⚠️ No device tokens for parent {request.parent_id}")
            return BadgeUnlockedResponse(
                success=False,
                message="No device tokens"
            )
        
        # Get child_name from request or parent data (for future use)
        # Priority: request.child_name > parent.child_name > None (will use "your child" in template)
        child_name = request.child_name
        if not child_name:
            child_name = parent_data.get("child_name")
        
        # Get notification message
        from services.notification_templates import get_badge_unlocked_message
        message_data = get_badge_unlocked_message(
            badge_name=request.badge_name,
            badge_icon=request.badge_icon,
            language=request.language,
            child_name=child_name
        )
        
        # Prepare data payload for deep linking
        data_payload = {
            "type": "badge_unlocked",
            "badge_id": request.badge_id,
            "badge_name": request.badge_name,
            "badge_icon": request.badge_icon
        }
        
        # Send notification
        push_service = get_push_notification_service()
        result = await push_service.send_notification(
            device_tokens=device_tokens,
            title=message_data["title"],
            body=message_data["body"],
            data=data_payload
        )
        
        # Store badge unlock event in Firestore
        badge_event_ref = db.collection("badge_history").document()
        badge_event_ref.set({
            "parent_id": request.parent_id,
            "badge_id": request.badge_id,
            "badge_name": request.badge_name,
            "badge_icon": request.badge_icon,
            "language": request.language,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "notification_sent": result.get("success", False),
            "created_at": firestore.SERVER_TIMESTAMP
        })
        
        if result.get("success"):
            print(f"✅ Badge unlock notification sent for badge {request.badge_id} to {result.get('success_count', 0)} device(s)")
            return BadgeUnlockedResponse(
                success=True,
                message="Badge unlock notification sent"
            )
        else:
            print(f"⚠️ Failed to send badge unlock notification: {result.get('error', 'Unknown error')}")
            return BadgeUnlockedResponse(
                success=False,
                message=f"Failed to send notification: {result.get('error', 'Unknown error')}"
            )
        
    except Exception as e:
        print(f"❌ Badge unlock event error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/events/streak-updated", response_model=StreakUpdatedResponse)
async def streak_updated_endpoint(request: StreakUpdatedRequest):
    """Receive streak update event and send milestone notification if applicable.
    
    COPPA-compliant: Notification sent to parent only.
    """
    try:
        if not db:
            print("⚠️ Firestore not available, skipping streak update")
            return StreakUpdatedResponse(
                success=False,
                message="Firestore not available"
            )
        
        # Streak milestones: 3, 7, 14, 30 days
        milestones = [3, 7, 14, 30]
        
        if request.streak_days not in milestones:
            # Not a milestone, just update streak in Firestore
            streak_ref = db.collection("streak_history").document(request.parent_id)
            streak_ref.set({
                "parent_id": request.parent_id,
                "streak_days": request.streak_days,
                "last_updated": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            return StreakUpdatedResponse(
                success=True,
                message="Streak updated (no milestone)"
            )
        
        # Milestone reached - send notification
        # Ensure parent exists (auto-create if missing for anonymous users)
        if not ensure_parent_exists(request.parent_id):
            # Still update streak even if Firestore unavailable
            return StreakUpdatedResponse(
                success=False,
                message="Firestore not available"
            )
        
        parent_ref = db.collection("parents").document(request.parent_id)
        parent_doc = parent_ref.get()
        
        if not parent_doc.exists:
            print(f"⚠️ Parent {request.parent_id} not found after ensure_parent_exists")
            return StreakUpdatedResponse(
                success=False,
                message="Parent not found"
            )
        
        parent_data = parent_doc.to_dict()
        
        # Check consent
        if not parent_data.get("notification_consent", False):
            print(f"⚠️ Parent {request.parent_id} has not consented to notifications")
            # Still update streak
            streak_ref = db.collection("streak_history").document(request.parent_id)
            streak_ref.set({
                "parent_id": request.parent_id,
                "streak_days": request.streak_days,
                "last_updated": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            return StreakUpdatedResponse(
                success=True,
                message="Streak updated (no consent for notification)"
            )
        
        device_tokens = parent_data.get("device_tokens", [])
        if not device_tokens:
            print(f"⚠️ No device tokens for parent {request.parent_id}")
            # Still update streak
            streak_ref = db.collection("streak_history").document(request.parent_id)
            streak_ref.set({
                "parent_id": request.parent_id,
                "streak_days": request.streak_days,
                "last_updated": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            return StreakUpdatedResponse(
                success=True,
                message="Streak updated (no device tokens)"
            )
        
        # Get child_name from request or parent data (for future use)
        # Priority: request.child_name > parent.child_name > None (will use "your child" in template)
        child_name = request.child_name
        if not child_name:
            child_name = parent_data.get("child_name")
        
        # Get notification message
        from services.notification_templates import get_streak_milestone_message
        message_data = get_streak_milestone_message(
            streak_days=request.streak_days,
            language=request.language,
            child_name=child_name
        )
        
        # Prepare data payload
        data_payload = {
            "type": "streak_milestone",
            "streak_days": str(request.streak_days)
        }
        
        # Send notification
        push_service = get_push_notification_service()
        result = await push_service.send_notification(
            device_tokens=device_tokens,
            title=message_data["title"],
            body=message_data["body"],
            data=data_payload
        )
        
        # Update streak in Firestore
        streak_ref = db.collection("streak_history").document(request.parent_id)
        streak_ref.set({
            "parent_id": request.parent_id,
            "streak_days": request.streak_days,
            "last_updated": firestore.SERVER_TIMESTAMP,
            "milestone_reached": request.streak_days,
            "milestone_notified_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        if result.get("success"):
            print(f"✅ Streak milestone notification sent ({request.streak_days} days) to {result.get('success_count', 0)} device(s)")
            return StreakUpdatedResponse(
                success=True,
                message=f"Streak milestone notification sent ({request.streak_days} days)"
            )
        else:
            print(f"⚠️ Failed to send streak milestone notification: {result.get('error', 'Unknown error')}")
            return StreakUpdatedResponse(
                success=False,
                message=f"Failed to send notification: {result.get('error', 'Unknown error')}"
            )
        
    except Exception as e:
        print(f"❌ Streak update event error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
