from fastapi import FastAPI, HTTPException, Response, Depends, Header, Request
from starlette.requests import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import httpx
import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore, storage, auth
from google.cloud.firestore_v1.base_query import FieldFilter
import ffmpeg
import tempfile
import uuid
from typing import Optional, Tuple, List, Dict
import json
import hashlib
from datetime import datetime, timedelta, timezone
import struct
import shutil
from pathlib import Path
import re
import time
import logging

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
print(f"✅ [Backend Startup] AUDIO_BASE_DIR: {AUDIO_BASE_DIR}")
print(f"   Path exists: {AUDIO_BASE_DIR.exists()}")
if AUDIO_BASE_DIR.exists():
    # List sample character directories
    char_dirs = [d.name for d in AUDIO_BASE_DIR.iterdir() if d.is_dir()][:5]
    print(f"   Sample character directories: {char_dirs}")

# Initialize Firebase
firebase_config = get_firebase_config()
db = firebase_config.db
bucket = firebase_config.bucket

async def generate_tts_with_elevenlabs(text: str, voice: str, emotion: str, speed: float, pitch: float, topic: str = None, lang: str = "en") -> bytes:
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
                else:
                    # CRITICAL: If no voice found, use Mino's default voice (not charlotte)
                    print(f"⚠️ No voice_id found for '{voice_lower}', using Mino's default voice")
                    mino_config = settings.CHARACTER_VOICES.get("mino", {})
                    fal_voice = mino_config.get("voice_id", "AZnzlk1XvdvUeBnXmlld")
            print(f"🎤 [FAL TTS] Using voice for '{voice_lower}': '{fal_voice}' (type: {'voice_id' if len(fal_voice) > 20 else 'voice_name'})")
            # Add language hint to text for better language detection (ElevenLabs multilingual model)
            # BEST PRACTICE: Language hint ensures correct language detection when multilingual model misdetects
            text_with_lang_hint = _add_language_hint(text, lang)
            return await _generate_tts_with_fal(text_with_lang_hint, char_settings, speed, pitch, fal_voice, character=voice_lower, lang=lang)
        
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
        # Add language hint to text for better language detection (ElevenLabs multilingual model)
        # BEST PRACTICE: Language hint ensures correct language detection when multilingual model misdetects
        text_with_lang_hint = _add_language_hint(text, lang)
        result = await _generate_tts_direct_elevenlabs(text_with_lang_hint, elevenlabs_voice, char_settings, speed, pitch, lang=lang)
        if result:
            return result
        # If direct API failed, return None (no fallback)
        print(f"❌ Direct ElevenLabs API failed, stopping")
        return None
            
    except Exception as e:
        print(f"❌ TTS generation failed: {e}")
        return None

def _add_language_hint(text: str, lang: str) -> str:
    """Add language hint to text for better ElevenLabs multilingual model language detection.
    
    BEST PRACTICE for ElevenLabs multilingual model:
    - The model auto-detects language but sometimes misdetects (e.g., English text detected as French)
    - Adding a language hint at the beginning helps the model correctly identify the language
    - Use minimal language-specific prefixes that are barely audible but ensure correct detection
    
    Strategy:
    1. Add language code prefix (e.g., "[EN]") at the beginning of text
    2. The prefix is minimal and helps model detection without significantly affecting audio
    3. Only add if text doesn't already start with a language hint
    """
    if not text or not lang:
        return text
    
    # Normalize language code
    lang_normalized = lang.lower().strip()
    
    # Map language codes to language hints (minimal prefixes for better detection)
    # These hints help ElevenLabs multilingual model correctly identify the language
    # Format: "[XX]" where XX is the language code (ISO 639-1)
    lang_hints = {
        "en": "[EN]",
        "fr": "[FR]",
        "tr": "[TR]",
        "de": "[DE]",
        "es": "[ES]",
        "pt": "[PT]",
        "ar": "[AR]",
    }
    
    # Get language hint (default to empty if not in map)
    hint = lang_hints.get(lang_normalized, "")
    
    if not hint:
        # Language not in map - log for debugging
        print(f"⚠️ [LanguageHint] Language '{lang}' not in hint map, skipping language hint")
        return text
    
    # Check if text already starts with a language hint (avoid duplicates)
    if text.startswith("[") and "]" in text[:10]:
        # Text already has a language hint, don't add another
        return text
    
    # Add language hint at the beginning of text
    # The hint is minimal (e.g., "[EN]") and helps ElevenLabs model detect the correct language
    # Note: The hint may be slightly audible in audio, but it ensures correct language detection
    # This is a trade-off: minimal audio artifact vs. correct language detection
    print(f"🌍 [LanguageHint] Adding language hint '{hint}' for language '{lang_normalized}'")
    return f"{hint} {text}"

# Text cleaning and audio conversion utilities are now imported from utils module

async def _generate_tts_with_fal(text: str, char_settings: dict, speed: float = 1.0, pitch: float = 1.0, voice_name_or_id: str = None, character: str = None, lang: str = "en") -> bytes:
    """Generate TTS via FAL.ai with multiple model fallbacks for child voices.
    
    If character has voice_cloning_reference, uses F5 TTS for voice cloning.
    Otherwise, uses standard ElevenLabs TTS models.
    
    BEST PRACTICE: Language hint is already added to text before calling this function.
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
                print(f"   Language: {lang} (hint already added to text)")
                print(f"   Speed: {speed_clamped:.2f}, Pitch: {pitch_clamped:.2f}")
                if voice_name_or_id:
                    print(f"   Voice: {voice_name_or_id} (length: {len(voice_name_or_id)}, type: {'voice_id' if len(voice_name_or_id) > 20 else 'voice_name'})")
                else:
                    print(f"   ⚠️ WARNING: No voice specified, FAL.ai will use default voice")
                print(f"   Text preview: {text[:100]}...")
                
                # Adjust arguments based on model
                arguments = base_arguments.copy()
                if "minimax" in model:
                    # MiniMax may have different parameter structure
                    arguments.pop("voice_settings", None)  # Remove if not supported
                    if voice_name_or_id:
                        arguments["voice_id"] = voice_name_or_id
                else:
                    # For ElevenLabs models via FAL.ai, use "voice" parameter with voice_id
                    # FAL.ai/elevenlabs accepts both voice name (string) and voice_id (string)
                    # According to FAL.ai docs: voice parameter accepts "The name or the ID (voice_id) of the voice"
                    if voice_name_or_id:
                        # CRITICAL: FAL.ai accepts voice_id directly in "voice" parameter
                        # We use "voice" parameter (not "voice_id") for FAL.ai/elevenlabs models
                        arguments["voice"] = voice_name_or_id
                        # Remove voice_id if it exists (we use "voice" parameter)
                        arguments.pop("voice_id", None)
                    else:
                        print(f"   ⚠️ WARNING: No voice specified, removing voice parameter")
                        arguments.pop("voice", None)
                
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

async def _generate_tts_direct_elevenlabs(text: str, voice_id: str, char_settings: dict, speed: float = 1.0, pitch: float = 1.0, lang: str = "en") -> bytes:
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
        print(f"   Language: {lang} (hint already added to text)")
        print(f"   Speed: {speed_clamped:.2f}")
        print(f"   Pitch: {pitch_clamped:.2f}")
        print(f"   Stability: {char_settings['stability']:.2f}")
        print(f"   Style: {char_settings['style']:.2f}")
        print(f"   Text preview: {text[:100]}...")
        print(f"   Text preview: {text[:100]}...")
        
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

# Bot/scanner traffic filter middleware
# Filters out common bot/scanner requests to reduce log spam
class BotTrafficFilterMiddleware(BaseHTTPMiddleware):
    """Filter bot/scanner traffic to reduce log spam."""
    
    # Common bot/scanner paths to ignore
    BOT_PATHS = {
        '/showLogin.cc', '/webfig/', '/zabbix/', '/favicon.ico',
        '/cgi-bin/', '/wp-json', '/sitemap.xml', '/robots.txt',
        '/.well-known/', '/api/session/', '/sitecore/', '/solr/',
        '/helpdesk/', '/jasperserver/', '/login.html', '/login.do',
        '/internal_forms_authentication', '/Telerik.Web.UI',
        '/license.txt', '/partymgr/', '/OA_HTML/', '/owncloud/',
        '/status.php', '/console', '/wiki', '/identity'
    }
    
    # Bot user agents to ignore
    BOT_USER_AGENTS = {
        'bot', 'crawler', 'spider', 'scanner', 'scraper', 'curl', 'wget',
        'python-requests', 'go-http-client', 'java/', 'okhttp'
    }
    
    async def dispatch(self, request: Request, call_next):
        # Check if this is a bot/scanner request
        path = request.url.path.lower()
        user_agent = request.headers.get('user-agent', '').lower()
        
        # Check for bot paths
        is_bot_path = any(bot_path in path for bot_path in self.BOT_PATHS)
        
        # Check for bot user agents
        is_bot_ua = any(bot_ua in user_agent for bot_ua in self.BOT_USER_AGENTS)
        
        # If it's a bot request to a non-existent endpoint, return 404 without logging
        if (is_bot_path or is_bot_ua) and path not in ['/', '/health', '/revenuecat/webhooks']:
            # Only filter 404s for bot traffic (let legitimate requests through)
            response = await call_next(request)
            if response.status_code == 404:
                # Suppress logging for bot 404s by not raising exception
                # Uvicorn will still log, but we can reduce our own logging
                return response
            return response
        
        return await call_next(request)

# Request logging middleware (for debugging POST requests)
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all incoming requests, especially POST requests."""
    
    async def dispatch(self, request: Request, call_next):
        # Log all POST requests in detail
        if request.method == "POST":
            print(f"🚀 [RequestLogging] ===== POST REQUEST RECEIVED =====")
            print(f"   URL: {request.url}")
            print(f"   Path: {request.url.path}")
            print(f"   Query params: {dict(request.query_params)}")
            
            # Log headers (especially Authorization)
            auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
            if auth_header:
                print(f"   ✅ Authorization header found: {auth_header[:50]}... (length: {len(auth_header)})")
            else:
                print(f"   ❌ NO Authorization header found!")
            
            # Log other important headers
            print(f"   Content-Type: {request.headers.get('content-type', 'N/A')}")
            print(f"   Content-Length: {request.headers.get('content-length', 'N/A')}")
            print(f"   User-Agent: {request.headers.get('user-agent', 'N/A')}")
            print(f"   X-Forwarded-For: {request.headers.get('x-forwarded-for', 'N/A')}")
            print(f"   X-Forwarded-Proto: {request.headers.get('x-forwarded-proto', 'N/A')}")
            print(f"   All headers keys: {list(request.headers.keys())}")
        
        response = await call_next(request)
        
        # Log POST response
        if request.method == "POST":
            print(f"📤 [RequestLogging] POST response:")
            print(f"   Status: {response.status_code}")
            print(f"   URL: {request.url}")
            print(f"   ===== END POST REQUEST =====")
        
        return response

# Add request logging middleware (first, to catch all requests)
app.add_middleware(RequestLoggingMiddleware)

# Add bot traffic filter middleware (before CORS)
app.add_middleware(BotTrafficFilterMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for now (iOS apps don't have CORS restrictions)
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],  # Allow all headers (iOS apps need Authorization header)
    expose_headers=["*"],  # Expose all headers in response
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
async def verify_firebase_token(request: Request) -> Optional[str]:
    """Verify Firebase Auth token and return user ID"""
    # Debug: Log all headers first
    print(f"🔍 [Auth] Request method: {request.method}")
    print(f"🔍 [Auth] Request URL: {request.url}")
    print(f"🔍 [Auth] All request headers:")
    for key, value in request.headers.items():
        if key.lower() == "authorization":
            print(f"   {key}: {value[:50]}... (length: {len(value)})")
        else:
            print(f"   {key}: {value}")
    
    # Try multiple ways to get the Authorization header
    authorization = None
    
    # Method 1: Try from headers dict (case-insensitive)
    if "authorization" in request.headers:
        authorization = request.headers["authorization"]
    elif "Authorization" in request.headers:
        authorization = request.headers["Authorization"]
    
    # Method 2: Try from get() method (case-insensitive)
    if not authorization:
        authorization = request.headers.get("authorization") or request.headers.get("Authorization")
    
    # Method 3: Try lowercase search
    if not authorization:
        for key, value in request.headers.items():
            if key.lower() == "authorization":
                authorization = value
                break
    
    if not authorization:
        print("⚠️ [Auth] No Authorization header found after all attempts")
    else:
        print(f"✅ [Auth] Authorization header found (length: {len(authorization)} chars)")
        print(f"   Preview: {authorization[:50]}...")
    
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
from models.story_create_models import (
    StoryRequest, CreateStoryResponse, StoryResponse, StoryListResponse, DuplicateStoryRequest
)
from services.story_composer import (
    to_character_slug,
    content_story_path,
    generate_story_with_openai,
)
from utils.topic_mapping import map_topic, get_topic_candidates
from services.push_notification_service import get_push_notification_service
from services.notification_scheduler import schedule_delayed_notification

# Use CHARACTER_VOICES from settings (alias for backward compatibility)
CHARACTER_VOICES = settings.CHARACTER_VOICES

# TTS Service with idempotent Storage caching
async def generate_tts(
    text: str,
    style: dict,
    lang: str,
    character: str = None,
    topic: str = None,
    scene_index: int = None,
    story_id: str = None,
) -> str:
    """Generate (or reuse) TTS audio and return a public URL.

    Strategy:
      - For pre-generated content: use character/topic/scene-based key
      - For dynamic content without scene refs: return mock/silent URL (no legacy save)
      - If existing file exists -> return its URL
    """
    # CRITICAL: Normalize character name to slug (e.g., "Spider Fighter" → "spiderman")
    # This ensures audio files are stored in the correct character directory
    character_normalized = to_character_slug(character) if character else None
    text = clean_text_for_tts(text, character_normalized)
    
    # Topic mapping: Map StorySelectionView topic names to actual file names
    # This aligns with how stories are generated and stored (same as ContentLoader.swift)
    # Use centralized topic mapping (from story_composer)
    topic_normalized = topic.lower() if topic else None
    topic_file = map_topic(topic_normalized) if topic_normalized else None
    
    print(f"🔊 [TTS] Generating audio: character={character_normalized}, topic={topic_normalized} → {topic_file}, lang={lang}, scene_index={scene_index}")

    if character_normalized and topic_file is not None and scene_index is not None:
        # If we have a specific story_id (custom LLM story), make audio **unique per story**
        # so that each story preserves its own recorded audio and later stories do not overwrite it.
        safe_story_suffix = None
        if story_id:
            # Strip common "story_" prefix and any non-filename-friendly chars
            safe_story_suffix = story_id.replace("story_", "").replace(" ", "_")
        
        if safe_story_suffix:
            key = f"{character_normalized}_{topic_file}_{safe_story_suffix}_{scene_index}"
            audio_basename = f"{topic_file}_{safe_story_suffix}_{scene_index}"
        else:
            # Legacy/shared bundle behaviour (pre-generated content)
            key = f"{character_normalized}_{topic_file}_{scene_index}"
            audio_basename = f"{topic_file}_{scene_index}"

        # Language-specific audio path: {character}/{lang}/{topic}_{scene_index}[_{story}] .wav
        # CRITICAL: Only use existing audio if it's in the correct language directory
        # This ensures we don't use wrong-language audio files
        character_dir = AUDIO_BASE_DIR / character_normalized / lang
        audio_filename = f"{audio_basename}.wav"
        local_audio_path = character_dir / audio_filename
        
        # Also try .mp3 extension
        local_audio_path_mp3 = character_dir / f"{audio_basename}.mp3"
        
        if (local_audio_path.exists() and local_audio_path.stat().st_size > 0) or \
           (local_audio_path_mp3.exists() and local_audio_path_mp3.stat().st_size > 0):
            # Found existing audio in correct language directory
            audio_ext = '.mp3' if local_audio_path_mp3.exists() else '.wav'
            print(f"✅ [TTS] Using existing audio: {audio_basename}{audio_ext} (lang={lang}, character={character_normalized}, story_id={story_id})")
            return f"{settings.BACKEND_BASE_URL}/local-audio/{key}{audio_ext}?lang={lang}"
        else:
            # Audio file doesn't exist in correct language directory
            # Check if it exists in wrong language (for debugging)
            wrong_lang_found = False
            for other_lang in ["en", "fr", "tr", "de", "es"]:
                if other_lang != lang:
                    other_lang_path = AUDIO_BASE_DIR / character_normalized / other_lang / audio_filename
                    if other_lang_path.exists() and other_lang_path.stat().st_size > 0:
                        print(f"⚠️ [TTS] Audio exists but in wrong language: {other_lang} (requested: {lang}), will generate new audio")
                        wrong_lang_found = True
                        break
            if not wrong_lang_found:
                print(f"ℹ️ [TTS] Audio file not found: {audio_filename} (lang={lang}), will generate new audio")
    else:
        # No scene context → do not write legacy files; return mock
        return f"{settings.BACKEND_BASE_URL}/mock-audio/{hashlib.sha256(text.encode()).hexdigest()}.wav"

    # Generate via ElevenLabs (FAL)
    # Get character voice settings - try exact match, then case-insensitive, then default
    character_voice_key = character_normalized or "mino"
    char_voice_config = settings.CHARACTER_VOICES.get(character_voice_key)
    if not char_voice_config:
        # Try case-insensitive match
        for key, value in settings.CHARACTER_VOICES.items():
            if key.lower() == character_voice_key.lower():
                char_voice_config = value
                print(f"✅ [TTS] Found character voice config (case-insensitive match): '{key}' → '{character_voice_key}'")
                break
    
    # Use character voice settings (matching original character inspiration) or fallback to style/defaults
    if char_voice_config:
        emotion = style.get("emotion", char_voice_config.get("emotion", "happy"))
        speed = style.get("speed", char_voice_config.get("speed", 1.0))
        pitch = style.get("pitch", char_voice_config.get("pitch", 1.0))
        voice_id = char_voice_config.get("voice_id")
        print(f"✅ [TTS] Using character-specific voice settings for '{character_voice_key}':")
        print(f"   Voice ID: {voice_id}")
        print(f"   Emotion: {emotion}")
        print(f"   Speed: {speed}")
        print(f"   Pitch: {pitch}")
    else:
        emotion = style.get("emotion", "happy")
        speed = style.get("speed", 1.0)
        pitch = style.get("pitch", 1.0)
        print(f"⚠️ [TTS] Character voice config NOT FOUND for '{character_voice_key}'")
        print(f"   Available CHARACTER_VOICES keys: {list(settings.CHARACTER_VOICES.keys())}")
        print(f"   Using fallback settings: emotion={emotion}, speed={speed}, pitch={pitch}")
    
    # Generate TTS with language support (ElevenLabs multilingual model auto-detects, but we log it)
    print(f"🌍 [TTS] Generating TTS for language: {lang}, character: {character_voice_key}, text preview: {text[:50]}...")
    audio_bytes = await generate_tts_with_elevenlabs(text, character_voice_key, emotion, speed, pitch, topic_file or topic, lang=lang)

    if audio_bytes and len(audio_bytes) > 100:
        is_mp3 = audio_bytes[:3] == b'ID3' or audio_bytes[:2] == b'\xff\xfb'
        audio_ext = '.mp3' if is_mp3 else '.wav'
        try:
            # Language-specific audio path: {character}/{lang}/{topic}_{scene_index}.ext
            character_dir = AUDIO_BASE_DIR / character_normalized / lang
            character_dir.mkdir(parents=True, exist_ok=True)
            # Use topic_file (mapped) for filename; if story_id is present, keep it **per-story unique**
            if topic_file:
                if story_id:
                    safe_story_suffix = story_id.replace("story_", "").replace(" ", "_")
                    audio_filename = f"{topic_file}_{safe_story_suffix}_{scene_index}{audio_ext}"
                else:
                    audio_filename = f"{topic_file}_{scene_index}{audio_ext}"
            else:
                audio_filename = f"{topic}_{scene_index}{audio_ext}"
            audio_path = character_dir / audio_filename
            with open(audio_path, 'wb') as f:
                f.write(audio_bytes)
            if topic_file:
                if story_id:
                    key = f"{character_normalized}_{topic_file}_{safe_story_suffix}_{scene_index}"
                else:
                    key = f"{character_normalized}_{topic_file}_{scene_index}"
            else:
                key = f"{character_normalized}_{topic}_{scene_index}"
            print(f"✅ [TTS] Saved audio: {audio_filename} (lang={lang}, character={character_normalized}, story_id={story_id}, path={character_dir})")
            return f"{settings.BACKEND_BASE_URL}/local-audio/{key}{audio_ext}?lang={lang}"
        except Exception as e:
            print(f"❌ Local storage failed: {e}")
            return f"{settings.BACKEND_BASE_URL}/mock-audio/{character_normalized}_{topic}_{scene_index}.wav"
    else:
        return f"{settings.BACKEND_BASE_URL}/mock-audio/{character_normalized}_{topic}_{scene_index}.wav"

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
async def serve_story(
    character: str, 
    topic: str, 
    lang: str = "en",
    user_id: Optional[str] = Depends(verify_firebase_token)
):
    """Serve story JSON file from backend storage or Firestore.
    
    BEST PRACTICE: Priority order
    1. Check Firestore for user-specific story (if user_id provided)
    2. Check local storage for pre-generated story
    3. Auto-compose story if not found
    
    Path format: backend/storage/content/{lang}/stories/{character}/{topic}.json
    Topic mapping: Maps iOS topic names to actual file names (same as audio serving)
    """
    try:
        # Validate topic is not empty (prevents 404 errors from empty topic requests)
        topic_normalized = topic.lower().strip()
        if not topic_normalized:
            print(f"⚠️ [serve_story] Empty topic received for character={character}, lang={lang}")
            print(f"   Request path: /story/{character}/{topic}?lang={lang}")
            raise HTTPException(status_code=400, detail="Topic parameter cannot be empty")
        
        # Use centralized topic mapping (from utils)
        topic_candidates = get_topic_candidates(topic_normalized)
        topic_mapped = map_topic(topic_normalized)
        
        print(f"🔍 [serve_story] Requested: character={character}, topic={topic} (normalized: {topic_normalized}, mapped: {topic_mapped}), lang={lang}")
        print(f"   Topic candidates: {topic_candidates}")
        print(f"   Full request path: /story/{character}/{topic}?lang={lang}")
        print(f"   User ID: {user_id if user_id else 'None (public story)'}")
        
        # PRIORITY 1: Check for custom story (ready) - user's own custom story
        if user_id and db:
            character_slug = to_character_slug(character)
            
            # Try deterministic ID first (faster, direct lookup)
            # Note: For /story/{character}/{topic} endpoint, we don't have custom_description,
            # so we can only match stories without custom_description
            custom_story_id = generate_custom_story_id(user_id, character_slug, topic_mapped, lang, custom_description=None)
            custom_story = await get_custom_story_by_id(custom_story_id)
            
            if custom_story:
                story_status = custom_story.get("status")
                story_kind = custom_story.get("kind", "custom")
                
                # CONTROL 4: Only return if it's a custom story and ready (custom > system priority)
                if (story_kind == "custom" or story_kind is None) and story_status == "ready":
                    print(f"✅ [serve_story] Found custom story (ready): {custom_story_id}")
                    print(f"   Title: {custom_story.get('title', 'N/A')}")
                    print(f"   Character: {custom_story.get('character_id', 'N/A')}")
                    print(f"   Topic: {custom_story.get('topic', 'N/A')}")
                    print(f"   Scenes count: {len(custom_story.get('scenes', []))}")
                    # CONTROL 4: Verify request_payload matches (if available)
                    request_payload = custom_story.get('request_payload')
                    if request_payload:
                        print(f"   📋 [serve_story] Request payload verification:")
                        print(f"      Original character: {request_payload.get('character_id', 'N/A')}")
                        print(f"      Original topic: {request_payload.get('topic', 'N/A')}")
                    # CRITICAL: Add id field to custom_story (Firestore document ID)
                    # iOS Story model requires id field for decoding
                    custom_story["id"] = custom_story_id
                    return JSONResponse(content=custom_story)
                else:
                    print(f"ℹ️ [serve_story] Custom story exists but status='{story_status}' (not ready), continuing to system story")
            
            # Fallback: Query by fields (for backward compatibility with old story IDs)
            # CRITICAL: Include custom_description stories and return the most recent one
            # OPTIMIZATION: Removed order_by to avoid composite index requirement
            # Results will be sorted in Python by created_at instead
            print(f"🔍 [serve_story] Checking Firestore for custom story (query fallback): user_id={user_id}, character={character_slug}, topic={topic_mapped}, lang={lang}")
            stories_ref = db.collection("stories")
            query = stories_ref.where(filter=FieldFilter("owner_user_id", "==", user_id))\
                              .where(filter=FieldFilter("character_id", "==", character_slug))\
                              .where(filter=FieldFilter("topic", "==", topic_mapped))\
                              .where(filter=FieldFilter("language", "==", lang))\
                              .where(filter=FieldFilter("status", "==", "ready"))
            
            try:
                matching_stories = list(query.stream())
                if matching_stories:
                    # Filter for custom stories only and sort by created_at in Python
                    custom_stories = []
                    for story_doc in matching_stories:
                        story_data = story_doc.to_dict()
                        story_kind = story_data.get("kind", "custom")
                        if story_kind == "custom" or story_kind is None:
                            story_id = story_doc.id
                            story_data["id"] = story_id
                            created_at = story_data.get("created_at", 0)
                            custom_stories.append((created_at, story_data, story_id))
                    
                    # Sort by created_at descending (most recent first) and return the first one
                    if custom_stories:
                        custom_stories.sort(key=lambda x: x[0], reverse=True)
                        created_at, story_data, story_id = custom_stories[0]
                        story_title = story_data.get("title", "N/A")
                        print(f"✅ [serve_story] Found custom story (query fallback): {story_id}")
                        print(f"   Title: {story_title}")
                        print(f"   Created at: {created_at}")
                        return JSONResponse(content=story_data)
            except Exception as e:
                print(f"⚠️ [serve_story] Error querying Firestore: {e}")
                import traceback
                print(f"   Traceback: {traceback.format_exc()}")
                pass
        
        # PRIORITY 2: Check for system story (ready) - pre-generated stories
        print(f"🔍 [serve_story] Checking for system story: character={character_slug}, topic={topic_mapped}, lang={lang}")
        if db:
            stories_ref = db.collection("stories")
            system_query = stories_ref.where(filter=FieldFilter("character_id", "==", character_slug))\
                                     .where(filter=FieldFilter("topic", "==", topic_mapped))\
                                     .where(filter=FieldFilter("language", "==", lang))\
                                     .where(filter=FieldFilter("status", "==", "ready"))
            
            try:
                matching_stories = list(system_query.stream())
                if matching_stories:
                    # Find system story (kind: "system" or kind missing, owner is None or "system")
                    for story_doc in matching_stories:
                        story_data = story_doc.to_dict()
                        story_kind = story_data.get("kind")
                        story_owner = story_data.get("owner_user_id")
                        
                        is_system = (story_kind == "system" or story_kind is None) and (story_owner is None or story_owner == "system")
                        if is_system:
                            story_id = story_doc.id
                            # CRITICAL: Add id field to story_data (Firestore document ID)
                            # iOS Story model requires id field for decoding
                            story_data["id"] = story_id
                            print(f"✅ [serve_story] Found system story (ready): {story_id}")
                            print(f"   Title: {story_data.get('title', 'N/A')}")
                            print(f"   Scenes count: {len(story_data.get('scenes', []))}")
                            return JSONResponse(content=story_data)
            except Exception as e:
                print(f"⚠️ [serve_story] Error querying system story: {e}")
                pass
        
        # PRIORITY 2: Try each candidate to find existing story in local storage
        # BEST PRACTICE: Prefer custom stories (with story_id) over pre-generated stories
        story_path = None
        custom_story_path = None
        character_slug = to_character_slug(character)
        for topic_candidate in topic_candidates:
            candidate_path = content_story_path(lang, character_slug, topic_candidate)
            if candidate_path.exists():
                file_size = candidate_path.stat().st_size
                if file_size > 0:
                    # CRITICAL: Validate story topic matches requested topic before serving
                    # This prevents serving wrong story (e.g., "friendship.json" for "sibling" request)
                    try:
                        with open(candidate_path, "r", encoding="utf-8") as f:
                            story_data = json.load(f)
                        story_topic = story_data.get("topic", "").lower().strip()
                        story_topic_mapped = map_topic(story_topic)
                        
                        if story_topic_mapped != topic_mapped:
                            print(f"⚠️ [serve_story] Story topic mismatch: file has '{story_topic}' (mapped: '{story_topic_mapped}'), but requested '{topic_normalized}' (mapped: '{topic_mapped}')")
                            print(f"   Skipping {candidate_path} - topic doesn't match")
                            continue  # Try next candidate
                        
                        # Check if this is a custom story (has story_id field)
                        story_id = story_data.get("story_id")
                        if story_id:
                            # Custom story - prioritize this over pre-generated stories
                            custom_story_path = candidate_path
                            print(f"✅ [serve_story] Found custom story in local storage: {candidate_path} (story_id={story_id}, lang={lang}, size: {file_size} bytes, topic: {story_topic})")
                        else:
                            # Pre-generated story - use as fallback if no custom story found
                            if not custom_story_path:
                                story_path = candidate_path
                                print(f"✅ [serve_story] Found pre-generated story: {story_path} (lang={lang}, size: {file_size} bytes, topic: {story_topic})")
                    except (json.JSONDecodeError, KeyError, Exception) as e:
                        print(f"⚠️ [serve_story] Failed to validate story topic in {candidate_path}: {e}")
                        # Continue to next candidate if validation fails
                        continue
                else:
                    # Only log if file is empty (unusual case)
                    print(f"⚠️ [serve_story] File exists but is empty: {candidate_path}")
        
        # Return custom story if found, otherwise return pre-generated story
        # CRITICAL: Add id field if missing (iOS Story model requires it)
        if custom_story_path:
            print(f"📤 [serve_story] Returning custom story from local storage: {custom_story_path}")
            with open(custom_story_path, "r", encoding="utf-8") as f:
                story_data = json.load(f)
            # Ensure id field exists
            if "id" not in story_data:
                story_data["id"] = story_data.get("story_id", f"{character_slug}_{topic_mapped}_{lang}")
            return JSONResponse(content=story_data)
        elif story_path:
            print(f"📤 [serve_story] Returning pre-generated story from local storage: {story_path}")
            with open(story_path, "r", encoding="utf-8") as f:
                story_data = json.load(f)
            # Ensure id field exists
            if "id" not in story_data:
                story_data["id"] = f"{character_slug}_{topic_mapped}_{lang}"
            return JSONResponse(content=story_data)
        
            # CRITICAL: Don't log "not found" for every candidate - only log summary if none found
        
        # Story not found - automatically compose it in background and return 202 Accepted
        # This prevents timeout issues - client can retry after composition completes
        # CRITICAL: Use mapped topic (not first candidate) for story file naming
        # This ensures consistency: "sibling" → "sibling.json" (not "sibling_issues.json")
        slug = to_character_slug(character)
        expected_path = content_story_path(lang, slug, topic_mapped)
        print(f"📝 [serve_story] Story not found after checking {len(topic_candidates)} candidates, starting background composition")
        print(f"   Character: {character}, Topic: {topic} (mapped: {topic_mapped}), Lang: {lang}")
        print(f"   Expected path: {expected_path.resolve()}")
        print(f"   Tried candidates: {topic_candidates}")
        final_story_path = content_story_path(lang, slug, topic_mapped)
        final_story_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Start background task to compose story (non-blocking)
        async def compose_story_background():
            try:
                print(f"🔄 [serve_story] Background composition started: {final_story_path}")
                # Generate story via OpenAI
                story_data = await generate_story_with_openai(
                    character,
                    topic_mapped,  # Use mapped topic (e.g., "nutrition" instead of "food")
                    lang,
                    duration_minutes=10  # Default 10 minutes
                )
                
                # Validate minimal schema
                if not story_data or "scenes" not in story_data or not isinstance(story_data["scenes"], list):
                    print(f"❌ [serve_story] Invalid story data from LLM")
                    return
                
                # Ensure durationMinutes is set
                if "durationMinutes" not in story_data:
                    story_data["durationMinutes"] = 10
                
                # CRITICAL: Validate and override topic field to match mapped topic
                # This ensures story file name and JSON topic field are consistent
                story_topic = story_data.get("topic", "").lower().strip()
                if story_topic != topic_mapped.lower():
                    print(f"⚠️ [serve_story] Story topic mismatch: LLM returned '{story_topic}', but expected '{topic_mapped}'")
                    print(f"   Overriding topic field to '{topic_mapped}' for consistency")
                    story_data["topic"] = topic_mapped
                
                # CRITICAL: Add id field if missing (iOS Story model requires it)
                if "id" not in story_data:
                    story_data["id"] = f"{character_slug}_{topic_mapped}_{lang}"
                
                # Persist story to file
                with open(final_story_path, "w", encoding="utf-8") as f:
                    json.dump(story_data, f, ensure_ascii=False, indent=2)
                
                print(f"✅ [serve_story] Background composition completed: {final_story_path} (lang={lang}, size: {final_story_path.stat().st_size} bytes)")
            except Exception as compose_error:
                print(f"❌ [serve_story] Background composition failed: {compose_error}")
                import traceback
                traceback.print_exc()
        
        # Start background task (fire and forget)
        import asyncio
        asyncio.create_task(compose_story_background())
        
        # Return 202 Accepted - story is being composed, client should retry
        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": "Story is being composed. Please retry in a few seconds.",
                "character": character,
                "topic": topic,
                "lang": lang
            }
        )
            
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
    
    IMPORTANT: This endpoint ONLY serves existing files. It does NOT generate TTS.
    If file doesn't exist, it returns mock_audio (which generates TTS on-the-fly).
    For proper TTS generation with caching, use /tts endpoint.
    """
    try:
        # Reduced logging: Only log errors, not every successful request
        # This reduces log spam during prefetch operations
        audio_id_clean = audio_id.replace('.wav', '').replace('.mp3', '')
        parts = audio_id_clean.split('_')
        if len(parts) >= 3:
            character = parts[0]
            scene_index_str = parts[-1]  # Last part is always scene_index (number)
            # Convert scene_index to integer
            try:
                scene_index = int(scene_index_str)
            except ValueError:
                scene_index = 0  # Fallback to 0 if conversion fails
            
            # BEST PRACTICE: Handle both system story and custom story formats
            # System story format: {character}_{topic}_{scene_index}
            #   Example: "luna_bedtime_0" -> character="luna", topic="bedtime", scene_index="0"
            # Custom story format: {character}_{topic}_{storyId}_{scene_index}
            #   Example: "luna_friendship_IiB3CvDS3SMFGqWZm7Rd8U06kKv2_luna_friendship_tr_0"
            #   -> character="luna", topic="friendship", storyId="IiB3CvDS3SMFGqWZm7Rd8U06kKv2_luna_friendship_tr", scene_index="0"
            #   File saved as: {topic}_{storyId}_{scene_index}.wav = "friendship_IiB3CvDS3SMFGqWZm7Rd8U06kKv2_luna_friendship_tr_0.wav"
            
            is_custom_story = len(parts) >= 4
            
            if is_custom_story:
                # Custom story format: character_topic_storyId_sceneIndex
                # CRITICAL: URL'den gelen audio_id içinde original_topic var (örn: bedtime)
                # Ama generate_tts dosyayı mapped_topic ile kaydediyor (örn: sibling)
                # Önce original_topic'ten mapped_topic'i bulmalıyız
                topic_and_story = '_'.join(parts[1:-1])  # Everything except first (character) and last (sceneIndex)
                
                # Extract original_topic (first part before userId)
                import re
                from utils.topic_mapping import map_topic
                user_id_match = re.search(r'([A-Za-z0-9]{20,30})', topic_and_story)
                original_topic = None
                if user_id_match:
                    original_topic = topic_and_story[:user_id_match.start()].rstrip('_')
                    # Map original_topic to mapped_topic
                    mapped_topic = map_topic(original_topic.lower()) if original_topic else None
                else:
                    # Fallback: try to extract from topic_and_story
                    mapped_topic = None
                
                # Extract storyIdWithoutPrefix: {userId}_{character}_{mapped_topic}_{lang}_{hash}
                character_pattern = f"_{character.lower()}_"
                if user_id_match and character_pattern in topic_and_story:
                    user_id = user_id_match.group(1)
                    char_pos = topic_and_story.find(character_pattern)
                    after_char = topic_and_story[char_pos + len(character_pattern):]
                    story_id_without_prefix = f"{user_id}_{character.lower()}_{after_char}"
                
                    # Try with mapped_topic format (how generate_tts saves it)
                    if mapped_topic:
                        for ext in ['.wav', '.mp3']:
                            audio_filename = f"{mapped_topic}_{story_id_without_prefix}_{scene_index}{ext}"
                            character_path = AUDIO_BASE_DIR / character.lower() / lang / audio_filename
                            if character_path.exists() and character_path.stat().st_size > 0:
                                media_type = "audio/mpeg" if ext == '.mp3' else "audio/wav"
                                print(f"✅ [serve_local_audio] Serving custom story audio (mapped): {character_path}")
                                return FileResponse(str(character_path), media_type=media_type)
                
                # Fallback: try with original topic_and_story format
                for ext in ['.wav', '.mp3']:
                    character_path = AUDIO_BASE_DIR / character.lower() / lang / f"{topic_and_story}_{scene_index}{ext}"
                    if character_path.exists() and character_path.stat().st_size > 0:
                        media_type = "audio/mpeg" if ext == '.mp3' else "audio/wav"
                        print(f"✅ [serve_local_audio] Serving custom story audio (original): {character_path}")
                        return FileResponse(str(character_path), media_type=media_type)
                
                # If exact match not found, try to generate audio from story
                print(f"⚠️ [serve_local_audio] Custom story audio not found: {character}/{topic_and_story}_{scene_index} (lang={lang})")
                print(f"   Attempting to generate audio from story...")
                
                # Extract story_id from topic_and_story
                # Format: "topic_userId_character_topic_lang" or "topic_storyId"
                # Try to find story_id in Firestore
                story_id = None
                scene_text = None
                
                # Try to extract story_id from topic_and_story
                # Audio ID format: {character}_{topic}_{storyIdWithoutPrefix}_{scene_index}
                # Example: "luna_sanft davon überzeugen, ins bett zu gehen_IiB3CvDS3SMFGqWZm7Rd8U06kKv2_luna_sanft_davon_uberzeugen_ins_bett_zu_gehen_de_9fe0a39a_0"
                # topic_and_story = "sanft davon überzeugen, ins bett zu gehen_IiB3CvDS3SMFGqWZm7Rd8U06kKv2_luna_sanft_davon_uberzeugen_ins_bett_zu_gehen_de_9fe0a39a"
                # Story ID format: story_{userId}_{character}_{topic}_{lang}_{hash}
                # So storyIdWithoutPrefix = {userId}_{character}_{topic}_{lang}_{hash}
                if db:
                    try:
                        # Extract storyIdWithoutPrefix from topic_and_story
                        # Pattern: {topic}_{userId}_{character}_{topic_normalized}_{lang}_{hash}
                        # We need to find the part that matches storyIdWithoutPrefix
                        # Look for character name in topic_and_story, then extract the part after it
                        import re
                        character_pattern = f"_{character.lower()}_"
                        if character_pattern in topic_and_story:
                            # Find the position of character pattern
                            char_pos = topic_and_story.find(character_pattern)
                            # Extract the part before character (should contain userId)
                            before_char = topic_and_story[:char_pos]
                            # Extract userId (typically a long alphanumeric string)
                            user_id_match = re.search(r'([A-Za-z0-9]{20,30})', before_char)
                            if user_id_match:
                                user_id = user_id_match.group(1)
                                # Extract the part after character pattern (should be topic_normalized_lang_hash)
                                after_char = topic_and_story[char_pos + len(character_pattern):]
                                # Reconstruct storyIdWithoutPrefix: {userId}_{character}_{topic_normalized}_{lang}_{hash}
                                story_id_without_prefix = f"{user_id}_{character.lower()}_{after_char}"
                                # Construct full story_id
                                potential_story_id = f"story_{story_id_without_prefix}"
                                
                                # Try to get story directly from Firestore
                                try:
                                    story_doc = db.collection("stories").document(potential_story_id).get()
                                    if story_doc.exists:
                                        story_data = story_doc.to_dict()
                                        story_id = potential_story_id
                                        scenes = story_data.get("scenes", [])
                                        if scene_index < len(scenes):
                                            scene = scenes[scene_index]
                                            scene_text = scene.get("text", "")
                                            if scene_text:
                                                print(f"✅ [serve_local_audio] Found story in Firestore: {story_id}, scene {scene_index}")
                                except Exception as direct_get_error:
                                    # If direct get fails, try query approach
                                    print(f"⚠️ [serve_local_audio] Direct get failed, trying query: {direct_get_error}")
                                    # Fallback: query by character and language, then match by user_id
                                    stories_ref = db.collection("stories")
                                    query = stories_ref.where("character_id", "==", character.lower()).where("language", "==", lang)
                                    # Use get() instead of stream() to avoid type comparison issues
                                    query_results = query.get()
                                    
                                    for story_doc in query_results:
                                        story_doc_id = story_doc.id
                                        if story_doc_id.startswith("story_") and user_id in story_doc_id:
                                            # Check if this story_id pattern matches topic_and_story
                                            story_id_without_prefix_check = story_doc_id.replace("story_", "", 1)
                                            if story_id_without_prefix_check in topic_and_story:
                                                # Found matching story
                                                story_data = story_doc.to_dict()
                                                story_id = story_doc_id
                                                scenes = story_data.get("scenes", [])
                                                if scene_index < len(scenes):
                                                    scene = scenes[scene_index]
                                                    scene_text = scene.get("text", "")
                                                    if scene_text:
                                                        print(f"✅ [serve_local_audio] Found story in Firestore: {story_id}, scene {scene_index}")
                                                        break
                    except Exception as e:
                        print(f"⚠️ [serve_local_audio] Error finding story in Firestore: {e}")
                        import traceback
                        traceback.print_exc()
                
                # If we found story text, generate audio using generate_tts
                if scene_text and story_id:
                    try:
                        print(f"🎵 [serve_local_audio] Generating audio for custom story: {story_id}, scene {scene_index}")
                        # Extract topic from topic_and_story (first part before userId)
                        # topic_and_story format: {topic}_{userId}_{character}_{topic_normalized}_{lang}_{hash}
                        # Try to extract topic by finding character pattern
                        topic_from_audio = "emotional_regulation"  # Default fallback
                        if character.lower() in topic_and_story:
                            char_pattern = f"_{character.lower()}_"
                            if char_pattern in topic_and_story:
                                # Extract part before character pattern (should contain topic)
                                before_char = topic_and_story[:topic_and_story.find(char_pattern)]
                                # Extract topic (first part before userId)
                                import re
                                user_id_match = re.search(r'([A-Za-z0-9]{20,30})', before_char)
                                if user_id_match:
                                    topic_from_audio = before_char[:user_id_match.start()].rstrip('_')
                                else:
                                    topic_from_audio = before_char.rstrip('_')
                        
                        from utils.topic_mapping import map_topic
                        mapped_topic = map_topic(topic_from_audio.lower() if topic_from_audio else "emotional_regulation")
                        
                        # Generate audio using generate_tts (this will save the file)
                        audio_url = await generate_tts(
                            text=scene_text,
                            style={"stability": 0.7, "similarity_boost": 0.85, "style": 0.6},
                            lang=lang,
                            character=character.lower(),
                            topic=mapped_topic,
                            scene_index=scene_index,
                            story_id=story_id,
                        )
                        
                        # generate_tts returns a URL, but we need to serve the file
                        # Extract the local path from the URL
                        if audio_url and "/local-audio/" in audio_url:
                            # Extract audio_id from URL
                            audio_id_from_url = audio_url.split("/local-audio/")[1].split("?")[0]
                            # Try to serve the file again (it should exist now)
                            for ext in ['.wav', '.mp3']:
                                character_path = AUDIO_BASE_DIR / character.lower() / lang / f"{topic_and_story}_{scene_index}{ext}"
                                if character_path.exists() and character_path.stat().st_size > 0:
                                    media_type = "audio/mpeg" if ext == '.mp3' else "audio/wav"
                                    print(f"✅ [serve_local_audio] Generated and serving custom story audio: {character_path}")
                                    return FileResponse(str(character_path), media_type=media_type)
                        
                        # If file still doesn't exist, fallback to mock_audio
                        print(f"⚠️ [serve_local_audio] Audio generation completed but file not found, falling back to mock_audio")
                        return await mock_audio(audio_id, lang=lang)
                    except Exception as e:
                        print(f"❌ [serve_local_audio] Error generating audio: {e}")
                        import traceback
                        traceback.print_exc()
                        # Fallback to mock_audio
                        return await mock_audio(audio_id, lang=lang)
                else:
                    # Story not found or scene text missing, fallback to mock_audio
                    print(f"⚠️ [serve_local_audio] Story not found or scene text missing, falling back to mock_audio")
                    return await mock_audio(audio_id, lang=lang)
            else:
                # System story format: character_topic_sceneIndex
                topic = '_'.join(parts[1:-1])  # Everything between character and scene_index is topic
                
                # Use centralized topic mapping (from story_composer) for system stories
                topic_normalized = topic.lower()
                topic_candidates = get_topic_candidates(topic_normalized)
            
            # Also try topic without underscores (for cases like "transitions_change" -> "transitionschange")
            topic_no_underscore = topic_normalized.replace('_', '')
            if topic_no_underscore not in topic_candidates:
                topic_candidates.append(topic_no_underscore)
            
            # Language-specific path: {character}/{lang}/{topic}_{scene_index}.ext
            # CRITICAL: Only serve audio files in the correct language directory
            # This prevents serving wrong-language audio files (e.g., French audio when English is requested)
            for topic_candidate in topic_candidates:
                for ext in ['.wav', '.mp3']:
                    character_path = AUDIO_BASE_DIR / character.lower() / lang / f"{topic_candidate}_{scene_index}{ext}"
                    if character_path.exists() and character_path.stat().st_size > 0:
                        media_type = "audio/mpeg" if ext == '.mp3' else "audio/wav"
                        # Reduced logging: Only log errors, successful requests are logged by uvicorn access logs
                        return FileResponse(str(character_path), media_type=media_type)
                    # Debug: Log why file wasn't found (only for first candidate to reduce spam)
                    elif topic_candidate == topic_candidates[0] and ext == '.wav':
                        # Create language directory if it doesn't exist (for new languages like pt, ar)
                        if not character_path.parent.exists():
                            try:
                                character_path.parent.mkdir(parents=True, exist_ok=True)
                                print(f"✅ [serve_local_audio] Created language directory: {character_path.parent}")
                            except Exception as mkdir_error:
                                print(f"⚠️ [serve_local_audio] Failed to create language directory: {mkdir_error}")
                        
                        # Log why file wasn't found
                        if not character_path.parent.exists():
                            print(f"🔍 [serve_local_audio] Path does not exist: {character_path.parent}")
                        elif not character_path.exists():
                            print(f"🔍 [serve_local_audio] File does not exist: {character_path}")
                        elif character_path.stat().st_size == 0:
                            print(f"🔍 [serve_local_audio] File is empty: {character_path}")
            
                # Fallback: Try old path structure (for backward compatibility) - only for system stories
            # WARNING: Legacy paths don't have language subdirectory, so we can't verify language
            # Only use legacy path if no language-specific path exists
            for topic_candidate in topic_candidates:
                for ext in ['.wav', '.mp3']:
                    legacy_path = AUDIO_BASE_DIR / character.lower() / f"{topic_candidate}_{scene_index}{ext}"
                    if legacy_path.exists() and legacy_path.stat().st_size > 0:
                        media_type = "audio/mpeg" if ext == '.mp3' else "audio/wav"
                        # Log warning only once per character/topic combination (not every request)
                        print(f"⚠️ [serve_local_audio] Using legacy path (no lang subdirectory): {character}/{topic_candidate} (lang={lang})")
                        return FileResponse(str(legacy_path), media_type=media_type)
            
                # Collect all tried paths for better error reporting (system stories only)
            tried_paths = []
            for topic_candidate in topic_candidates:
                for ext in ['.wav', '.mp3']:
                    tried_paths.append(str(AUDIO_BASE_DIR / character.lower() / lang / f"{topic_candidate}_{scene_index}{ext}"))
                    tried_paths.append(str(AUDIO_BASE_DIR / character.lower() / f"{topic_candidate}_{scene_index}{ext}"))  # Legacy paths
                    # CRITICAL: Do NOT fallback to other languages (e.g., "en" when "fr" is requested)
                    # This would cause wrong-language audio to be served
                    # Only use the requested language
            
            topic_mapped = map_topic(topic_normalized)
            # CRITICAL: Check what files actually exist in the character directory
            character_dir = AUDIO_BASE_DIR / character.lower()
            lang_dir = character_dir / lang
            
            # List actual files in the directory for debugging
            existing_paths = [p for p in tried_paths if Path(p).exists()]
            if existing_paths:
                # Some paths exist but weren't used - log this with actual file list
                print(f"⚠️ [serve_local_audio] File NOT FOUND: character={character}, topic={topic} (normalized: {topic_normalized}, mapped: {topic_mapped}), scene_index={scene_index}, lang={lang}")
                print(f"   Found {len(existing_paths)} existing paths but none matched criteria")
                print(f"   AUDIO_BASE_DIR: {AUDIO_BASE_DIR}")
                print(f"   Character dir exists: {character_dir.exists()}")
                if lang_dir.exists():
                    actual_files = list(lang_dir.glob(f"*{scene_index}.*"))
                    if actual_files:
                        print(f"   Actual files in {lang_dir}: {[f.name for f in actual_files]}")
                    else:
                        print(f"   No files with scene_index {scene_index} in {lang_dir}")
                else:
                    print(f"   Language dir does not exist: {lang_dir}")
                    # Check if character dir has any files
                    if character_dir.exists():
                        all_files = list(character_dir.rglob(f"*{scene_index}.*"))
                        if all_files:
                            print(f"   Found files in character dir (wrong structure): {[str(f.relative_to(character_dir)) for f in all_files[:5]]}")
            else:
                # No paths exist - check if directory structure is correct
                print(f"⚠️ [serve_local_audio] Audio not found: {character}/{topic_mapped}_{scene_index} (lang={lang}), will generate TTS")
                print(f"   AUDIO_BASE_DIR: {AUDIO_BASE_DIR}")
                print(f"   Character dir exists: {character_dir.exists()}")
                if character_dir.exists():
                    # List what's actually in the character directory
                    subdirs = [d.name for d in character_dir.iterdir() if d.is_dir()]
                    files = [f.name for f in character_dir.iterdir() if f.is_file()]
                    if subdirs:
                        print(f"   Subdirectories in character dir: {subdirs[:5]}")
                    if files:
                        print(f"   Files in character dir (wrong structure): {files[:5]}")
            
            # IMPORTANT: If file doesn't exist, return mock_audio (which generates TTS on-the-fly from story text)
            # This should NOT happen for pre-generated content - files should exist!
            # But if it does, mock_audio will load the story JSON and generate correct audio
            print(f"⚠️ [serve_local_audio] Audio file not found for lang={lang}, falling back to mock_audio (will generate TTS on-the-fly from story)")
            print(f"   NOTE: This means audio was not pre-generated. mock_audio will load story JSON in lang={lang} and generate correct audio.")
            print(f"   CRITICAL: mock_audio will use lang={lang} parameter to load correct language story JSON")
            return await mock_audio(audio_id, lang=lang)
    except Exception as e:
        print(f"❌ [serve_local_audio] Error: {e}")
        import traceback
        traceback.print_exc()
        return await mock_audio(audio_id, lang=lang)

@app.get("/mock-audio/{audio_id}")
async def mock_audio(audio_id: str, lang: str = "en"):
    """Generate TTS audio on-the-fly when pre-generated file doesn't exist.
    
    BEST PRACTICE: Loads text from story JSON file to generate correct audio.
    This ensures that even if audio file doesn't exist, we generate the right content.
    """
    try:
        # Parse audio_id: {character}_{topic}_{scene_index}
        audio_id_clean = audio_id.replace('.wav', '').replace('.mp3', '')
        parts = audio_id_clean.split('_')
        if len(parts) < 3:
            print(f"⚠️ [mock_audio] Invalid audio_id format: {audio_id}, using fallback text")
            fallback_text = "Hello! I'm here to help you! 🌈"
        else:
            character = parts[0]
            scene_index = int(parts[-1])  # Last part is scene_index
            topic = '_'.join(parts[1:-1])  # Everything between character and scene_index is topic
            
            # Use centralized topic mapping
            from utils.topic_mapping import map_topic, get_topic_candidates
            topic_normalized = topic.lower()
            topic_mapped = map_topic(topic_normalized)
            topic_candidates = get_topic_candidates(topic_normalized)
            
            print(f"🔊 [mock_audio] Generating TTS on-the-fly: character={character}, topic={topic} (mapped={topic_mapped}), scene_index={scene_index}, lang={lang}")
            
            # Try to load story JSON to get actual scene text
            from services.story_composer import content_story_path, to_character_slug
            character_slug = to_character_slug(character)
            
            story_text = None
            # Try each topic candidate to find story file
            # CRITICAL: Use lang parameter to load correct language story JSON
            # This ensures we get the correct language text for TTS generation
            for topic_candidate in topic_candidates:
                story_path = content_story_path(lang, character_slug, topic_candidate)
                print(f"🔍 [mock_audio] Checking story path: {story_path} (lang={lang})")
                if story_path.exists():
                    try:
                        with open(story_path, 'r', encoding='utf-8') as f:
                            story_data = json.load(f)
                            scenes = story_data.get("scenes", [])
                            if scene_index < len(scenes):
                                scene = scenes[scene_index]
                                story_text = scene.get("text", "")
                                if story_text:
                                    print(f"✅ [mock_audio] Loaded text from story: {story_path} (scene {scene_index})")
                                    break
                    except Exception as e:
                        print(f"⚠️ [mock_audio] Error loading story {story_path}: {e}")
                        continue
            
            if not story_text:
                print(f"⚠️ [mock_audio] Story not found or scene text missing, using fallback text")
                fallback_text = f"Hello! Let's talk about {topic.replace('_', ' ')}! 🌈"
            else:
                fallback_text = story_text
        
        # Get character voice settings
        character_lower = character.lower() if len(parts) >= 3 else "mino"
        voice_settings = CHARACTER_VOICES.get(character_lower, CHARACTER_VOICES.get("mino", {}))
        voice_id = voice_settings.get("voice_id", "gender-neutral-mid")
        emotion = voice_settings.get("emotion", "happy")
        speed = voice_settings.get("speed", 1.0)
        pitch = voice_settings.get("pitch", 1.1)
        
        print(f"🎤 [mock_audio] Using voice for {character_lower}: {voice_id}")
        print(f"🌍 [mock_audio] Generating TTS with language: {lang}, text preview: {fallback_text[:100]}...")
        
        # Generate TTS with character-specific voice
        # CRITICAL: Pass lang parameter to ensure correct language detection
        # The _add_language_hint function will add language hint (e.g., [EN]) to text
        # This prevents ElevenLabs multilingual model from misdetecting the language
        # CRITICAL: Pass character name (not voice_id) to generate_tts_with_elevenlabs
        # The function will look up voice_id from CHARACTER_VOICES internally
        audio_bytes = await generate_tts_with_elevenlabs(
            text=fallback_text,
            voice=character_lower,  # Pass character name, not voice_id
            emotion=emotion,
            speed=speed,
            pitch=pitch,
            topic=topic_mapped if len(parts) >= 3 else None,
            lang=lang  # CRITICAL: Pass lang parameter for correct language detection
        )
        
        if audio_bytes:
            print(f"✅ [mock_audio] Generated TTS audio: {len(audio_bytes)} bytes")
            return Response(content=audio_bytes, media_type="audio/wav")
        else:
            print("⚠️ [mock_audio] TTS generation failed, using silent fallback")
            # Fallback to silent audio
            audio_bytes = create_minimal_silent_mp3(3.0)
            return Response(content=audio_bytes, media_type="audio/wav")
            
    except Exception as e:
        print(f"❌ [mock_audio] Error: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to silent audio
        audio_bytes = create_minimal_silent_mp3(3.0)
        return Response(content=audio_bytes, media_type="audio/wav")

@app.options("/iap/verify")
async def verify_receipt_options():
    """Handle CORS preflight requests for /iap/verify endpoint."""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )

@app.get("/iap/verify")
async def verify_receipt_get():
    """Handle GET requests to /iap/verify - returns method not allowed with helpful message."""
    raise HTTPException(
        status_code=405,
        detail="Method not allowed. This endpoint only accepts POST requests. Please use POST method with receipt data in the request body."
    )

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
                                
                                # CRITICAL: For new purchases, will_renew should default to True
                                # iOS app will update this flag from RevenueCat (source of truth)
                                # But for receipt verification, we assume new purchases will renew
                                # This prevents false "expired" status for active subscriptions
                                existing_doc = user_ref.get()
                                will_renew = True  # Default for new purchases
                                if existing_doc.exists:
                                    existing_data = existing_doc.to_dict()
                                    # Preserve existing will_renew if it exists (from iOS or RevenueCat webhook)
                                    will_renew = existing_data.get("will_renew", True)
                                
                                user_ref.set({
                                    "user_id": request.user_id,
                                    "product_id": product_id,
                                    "expires_date_ms": expires_date_ms,
                                    "trial_end_date_ms": trial_end_date_ms,
                                    "is_trial_period": is_trial_period,
                                    "is_in_intro_offer_period": is_in_intro_offer_period,
                                    "environment": environment,
                                    "billing_issue": False,  # Fix: default false instead of null
                                    "will_renew": will_renew,  # CRITICAL: Default True for new purchases, preserve existing if present
                                    "verified_at": firestore.SERVER_TIMESTAMP,
                                    "updated_at": firestore.SERVER_TIMESTAMP
                                }, merge=True)
                                print(f"✅ Subscription status saved to Firestore for user: {request.user_id} (will_renew: {will_renew})")
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

@app.get("/")
async def root():
    """Root endpoint - redirects to health check"""
    return {"status": "healthy", "service": "mino"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "mino"}

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
            "story_id": request.story_id if request.story_id and request.story_id.strip() else None,  # Fix: null instead of empty string
            "topic": request.topic,
            "character": request.character,
            "language": request.language,
            "notified": False,
            "created_at": firestore.SERVER_TIMESTAMP  # Fix: removed duplicate timestamp field
        }
        
        # Add summary if provided (best practice: meaningful note for parents)
        if request.summary and request.summary.strip():
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

@app.options("/parents/register-device")
async def register_device_options():
    """Handle CORS preflight requests for /parents/register-device endpoint."""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )

@app.get("/parents/register-device")
async def register_device_get():
    """Handle GET requests to /parents/register-device - returns method not allowed with helpful message."""
    raise HTTPException(
        status_code=405,
        detail="Method not allowed. This endpoint only accepts POST requests. Please use POST method with device registration data in the request body."
    )

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
        try:
            badge_event_ref = db.collection("badge_history").document()
            badge_event_ref.set({
                "parent_id": request.parent_id,
                "badge_id": request.badge_id,
                "badge_name": request.badge_name,
                "badge_icon": request.badge_icon,
                "language": request.language,
                "notification_sent": result.get("success", False),
                "created_at": firestore.SERVER_TIMESTAMP
            })
        except Exception as firestore_error:
            print(f"⚠️ Failed to store badge event in Firestore: {firestore_error}")
            # Continue - notification was sent, just couldn't store event
        
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
        # CRITICAL: Always return a response, even on error
        return BadgeUnlockedResponse(
            success=False,
            message=f"Error processing badge unlock: {str(e)}"
        )


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
                "updated_at": firestore.SERVER_TIMESTAMP  # Fix: removed duplicate last_updated field
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
                "updated_at": firestore.SERVER_TIMESTAMP  # Fix: removed duplicate last_updated field
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
                "updated_at": firestore.SERVER_TIMESTAMP  # Fix: removed duplicate last_updated field
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
            "milestone_reached": request.streak_days,
            "milestone_notified_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP  # Fix: removed duplicate last_updated field
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


# MARK: - Story Creation Endpoints
from models.story_create_models import (
    StoryRequest, CreateStoryResponse, StoryResponse, StoryListResponse, DuplicateStoryRequest
)

def normalize_topic_for_id(topic: str) -> str:
    """Normalize topic string for use in story ID (Firestore document ID).
    
    Converts Turkish characters to ASCII equivalents:
    ç→c, ğ→g, ş→s, ü→u, ö→o, ı→i, İ→I
    
    Args:
        topic: Topic string (e.g., "çikolata yememe", "nutrition")
        
    Returns:
        Normalized topic slug safe for Firestore document IDs
    """
    # Turkish character mapping to ASCII
    turkish_to_ascii = {
        'ç': 'c', 'Ç': 'C',
        'ğ': 'g', 'Ğ': 'G',
        'ş': 's', 'Ş': 'S',
        'ü': 'u', 'Ü': 'U',
        'ö': 'o', 'Ö': 'O',
        'ı': 'i', 'İ': 'I'
    }
    
    # Replace Turkish characters
    normalized = topic
    for turkish, ascii_char in turkish_to_ascii.items():
        normalized = normalized.replace(turkish, ascii_char)
    
    # Convert to lowercase and strip
    normalized = normalized.lower().strip()
    
    # Replace spaces and other invalid chars with underscores
    normalized = re.sub(r'[^a-zA-Z0-9_-]', '_', normalized)
    
    # Remove multiple consecutive underscores
    normalized = re.sub(r'_+', '_', normalized)
    
    # Remove leading/trailing underscores
    normalized = normalized.strip('_')
    
    return normalized


def generate_custom_story_id(user_id: str, character: str, topic: str, lang: str, custom_description: Optional[str] = None) -> str:
    """Generate deterministic story ID for custom stories.
    
    Format: story_{userId}_{character}_{topic}_{lang}[_{desc_hash}]
    This ensures idempotency: same parameters = same ID = same story.
    
    CRITICAL: If custom_description is provided, it's included in the ID hash to ensure
    different descriptions create different stories, even if they map to the same topic.
    
    Args:
        user_id: User ID
        character: Character ID (e.g., "spongebob", "mino")
        topic: Topic string (e.g., "çikolata yememe", "nutrition")
        lang: Language code (e.g., "tr", "en")
        custom_description: Optional custom description (e.g., "Kefir iç ikna et")
        
    Returns:
        Deterministic story ID (e.g., "story_user123_spongebob_friendship_tr" or
        "story_user123_spongebob_friendship_tr_a1b2c3d4" if custom_description provided)
    """
    import hashlib
    
    character_slug = to_character_slug(character)
    
    # CRITICAL: For custom stories, don't map topic - use original
    # This ensures "Tuğba ilacını içmiyor" stays as-is, not mapped to "nutrition"
    if custom_description and custom_description.strip():
        # Custom story: use original topic (no mapping)
        topic_normalized = normalize_topic_for_id(topic)
    else:
        # System story: map topic to canonical
        # First try to map to canonical topic, then normalize for ID
        topic_mapped = map_topic(topic.lower().strip())
    # If mapping didn't change the topic (no canonical match), use original
    if topic_mapped == topic.lower().strip():
        topic_normalized = normalize_topic_for_id(topic)
    else:
        # Use mapped canonical topic (already ASCII-safe)
        topic_normalized = normalize_topic_for_id(topic_mapped)
    
    lang_normalized = lang.lower().strip()
    
    # Build base story ID
    story_id = f"story_{user_id}_{character_slug}_{topic_normalized}_{lang_normalized}"
    
    # CRITICAL: If custom_description is provided, add hash to ensure different descriptions
    # create different stories (even if they map to the same topic)
    if custom_description and custom_description.strip():
        desc_clean = custom_description.strip().lower()
        # Create short hash (first 8 chars of MD5) for uniqueness
        desc_hash = hashlib.md5(desc_clean.encode('utf-8')).hexdigest()[:8]
        story_id = f"{story_id}_{desc_hash}"
    
    # Final sanitization for Firestore document ID (should already be safe, but double-check)
    story_id = re.sub(r'[^a-zA-Z0-9_-]', '_', story_id)
    story_id = re.sub(r'_+', '_', story_id)  # Remove multiple underscores
    story_id = story_id.strip('_')
    
    return story_id


async def get_custom_story_by_id(story_id: str) -> Optional[Dict]:
    """Get custom story by deterministic ID from Firestore.
    
    Args:
        story_id: Deterministic story ID (e.g., "story_user123_spongebob_friendship_tr")
        
    Returns:
        Story document data if found, None otherwise
    """
    if not db:
        return None
    
    try:
        story_ref = db.collection("stories").document(story_id)
        story_doc = story_ref.get()
        
        if story_doc.exists:
            return story_doc.to_dict()
        return None
    except Exception as e:
        print(f"⚠️ [get_custom_story_by_id] Error fetching story {story_id}: {e}")
        return None


async def check_rate_limit(user_id: str, is_subscriber: bool) -> Tuple[bool, str]:
    """
    Check rate limiting for story creation (abuse prevention).
    Returns (allowed, reason).
    
    Rate limits:
    - Free users: 3 stories/month (handled by quota check)
    - Subscribers: Fair use policy
      - Max 10 stories/hour (prevents spam/abuse)
      - Max 50 stories/day (fair use limit)
      - Max 200 stories/week (reasonable weekly limit)
    """
    if not db:
        return True, "Firestore unavailable"
    
    if not is_subscriber:
        # Free users: rate limiting handled by quota check
        return True, "Free user (quota check applies)"
    
    try:
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        
        stories_ref = db.collection("stories")
        
        # Check hourly limit (10 stories/hour)
        hour_query = stories_ref.where(filter=FieldFilter("owner_user_id", "==", user_id))\
                               .where(filter=FieldFilter("created_at", ">=", hour_ago.timestamp()))
        hour_count = len(list(hour_query.stream()))
        if hour_count >= 10:
            return False, f"Rate limit exceeded: {hour_count} stories in the last hour (max 10/hour)"
        
        # Check daily limit (50 stories/day)
        day_query = stories_ref.where(filter=FieldFilter("owner_user_id", "==", user_id))\
                               .where(filter=FieldFilter("created_at", ">=", day_ago.timestamp()))
        day_count = len(list(day_query.stream()))
        if day_count >= 50:
            return False, f"Rate limit exceeded: {day_count} stories today (max 50/day)"
        
        # Check weekly limit (200 stories/week)
        week_query = stories_ref.where(filter=FieldFilter("owner_user_id", "==", user_id))\
                                .where(filter=FieldFilter("created_at", ">=", week_ago.timestamp()))
        week_count = len(list(week_query.stream()))
        if week_count >= 200:
            return False, f"Rate limit exceeded: {week_count} stories this week (max 200/week)"
        
        print(f"✅ [check_rate_limit] Rate limits OK: {hour_count}/10 hour, {day_count}/50 day, {week_count}/200 week")
        return True, f"Rate limits OK ({hour_count}/10 hour, {day_count}/50 day, {week_count}/200 week)"
    except Exception as e:
        print(f"⚠️ [check_rate_limit] Error checking rate limits: {e}")
        # Allow on error (fail open for better UX)
        return True, f"Rate limit check error: {e}"


async def check_user_quota(user_id: str, length: str) -> Tuple[bool, int]:
    """
    Check if user has quota remaining. Returns (has_quota, quota_remaining).
    
    Quota rules:
    - Free users: 3 quick stories/month
    - Subscribers: Unlimited quota (with fair use rate limits)
    """
    print(f"🔍 [check_user_quota] Checking quota for user: {user_id}, length: {length}")
    if not db:
        print(f"⚠️ [check_user_quota] Firestore unavailable, allowing request")
        return True, 999  # Allow if Firestore unavailable
    
    try:
        # Check subscription status
        subscription_ref = db.collection("subscriptions").document(user_id)
        subscription_doc = subscription_ref.get()
        
        has_subscription = False
        is_trial = False
        is_grace_period = False
        product_id = None
        if subscription_doc.exists:
            sub_data = subscription_doc.to_dict()
            print(f"🔍 [check_user_quota] Subscription document found: {list(sub_data.keys())}")
            expires_ms = sub_data.get("expires_date_ms")
            product_id = sub_data.get("product_id", "")
            is_trial = sub_data.get("is_trial_period", False)
            trial_end_ms = sub_data.get("trial_end_date_ms")
            will_renew = sub_data.get("will_renew", False)  # RevenueCat grace period indicator
            
            if expires_ms:
                expires_at = datetime.fromtimestamp(expires_ms / 1000)
                now = datetime.now()
                
                # If will_renew is not set, check if subscription is recent (updated in last 24 hours)
                # This handles cases where RevenueCat webhook hasn't updated will_renew yet
                if not will_renew and expires_at < now:
                    updated_at = sub_data.get("updated_at")
                    if updated_at:
                        # Firestore Timestamp to datetime
                        if hasattr(updated_at, 'timestamp'):
                            updated_datetime = datetime.fromtimestamp(updated_at.timestamp())
                        else:
                            updated_datetime = datetime.fromtimestamp(updated_at / 1000)
                        # If subscription was updated recently (last 24 hours), assume it might renew
                        hours_since_update = (now - updated_datetime).total_seconds() / 3600
                        if hours_since_update < 24:
                            print(f"⚠️ [check_user_quota] Subscription expired but updated recently ({hours_since_update:.1f} hours ago)")
                            print(f"   Assuming grace period - RevenueCat may update will_renew soon")
                            will_renew = True  # Temporary grace period assumption
                            is_grace_period = True
                            has_subscription = True
                
                # RevenueCat manages subscription states - we only read the flags
                # 1. If expires_at > now: Active subscription
                # 2. If expires_at < now but will_renew = True: Grace period (RevenueCat manages this)
                # 3. If is_trial_period = True: Trial period (RevenueCat manages this)
                
                has_subscription = expires_at > now
                
                # RevenueCat grace period: If willRenew is True, user is in grace period (RevenueCat manages duration)
                # We don't calculate grace period duration - RevenueCat handles this
                if will_renew and expires_at < now:
                    is_grace_period = True
                    has_subscription = True  # Grant access during grace period (RevenueCat manages this)
                    print(f"⏳ [check_user_quota] User is in GRACE PERIOD (RevenueCat managed, will_renew={will_renew})")
                
                # RevenueCat trial period: If is_trial_period is True, user is in trial (RevenueCat manages duration)
                # We don't calculate trial duration - RevenueCat handles this
                if is_trial:
                    print(f"🎁 [check_user_quota] User is in TRIAL period (RevenueCat managed, is_trial_period={is_trial})")
                
                print(f"📅 [check_user_quota] Subscription expires_at: {expires_at}, now: {now}, is_active: {has_subscription}, is_trial: {is_trial}, is_grace_period: {is_grace_period}, will_renew: {will_renew}")
                
                # DEBUG: Check if subscription expired but should be renewed
                if expires_at < now and not will_renew:
                    days_expired = (now - expires_at).days
                    print(f"⚠️ [check_user_quota] Subscription EXPIRED {days_expired} days ago (expires_at: {expires_at})")
                    print(f"   will_renew: {will_renew} (False = no grace period, subscription truly expired)")
                    print(f"   is_trial_period: {is_trial} (False = not in trial)")
                    print(f"   ⚠️ User needs to renew subscription or RevenueCat should update will_renew flag")
                
                if product_id:
                    print(f"📦 [check_user_quota] Product ID: {product_id} (monthly/yearly)")
            else:
                print(f"⚠️ [check_user_quota] Subscription document exists but expires_date_ms is missing")
        else:
            print(f"⚠️ [check_user_quota] No subscription document found in 'subscriptions' collection for user: {user_id}")
            print(f"   Checking if subscription exists in 'parents' collection (backward compatibility)...")
            # Also check parents collection for backward compatibility
            parents_ref = db.collection("parents").document(user_id)
            parents_doc = parents_ref.get()
            if parents_doc.exists:
                parents_data = parents_doc.to_dict()
                subscription_data = parents_data.get("subscription")
                if subscription_data:
                    print(f"   Found subscription in parents collection: {list(subscription_data.keys())}")
                    expires_at_field = subscription_data.get("expires_at")
                    if expires_at_field:
                        # Firestore Timestamp to datetime
                        if hasattr(expires_at_field, 'timestamp'):
                            expires_at = datetime.fromtimestamp(expires_at_field.timestamp())
                        else:
                            expires_at = datetime.fromtimestamp(expires_at_field / 1000)
                        has_subscription = expires_at > datetime.now()
                        # Check if trial from parents collection (if available)
                        if subscription_data.get("status") == "trial" or subscription_data.get("tier") == "trial":
                            is_trial = True
                            print(f"   Trial detected from parents collection")
                        print(f"   Subscription from parents: expires_at={expires_at}, is_active={has_subscription}, is_trial={is_trial}")
                else:
                    print(f"   No subscription data in parents collection")
            else:
                print(f"   No document found in parents collection either")
        
        print(f"📊 [check_user_quota] Final subscription status: has_subscription={has_subscription}, is_trial={is_trial}, is_grace_period={is_grace_period}")
        
        # RevenueCat manages all subscription states - we only read the flags
        # Trial, grace period, and active subscription all get unlimited quota
        if is_trial or is_grace_period or has_subscription:
            status_type = "TRIAL" if is_trial else ("GRACE PERIOD" if is_grace_period else "ACTIVE SUBSCRIPTION")
            print(f"✅ [check_user_quota] User has {status_type} (RevenueCat managed) - unlimited quota (with fair use rate limits)")
            # Rate limiting will be checked separately in create_custom_story
            return True, 999
        
        # If we reach here, user has no active subscription, trial, or grace period
        print(f"ℹ️ [check_user_quota] User is a FREE user (no subscription/trial/grace period) - checking monthly quota")
        
        # Free users (no trial, no subscription): 
        # OPTION 1: 3 quick stories/month (teaser/retention)
        # OPTION 2: 0 stories (paywall - force subscription)
        # Currently using OPTION 1 for better UX and retention
        
        # Free users: check monthly quota (3 quick stories per month)
        if length != "quick":
            print(f"❌ [check_user_quota] Non-quick stories require subscription")
            return False, 0
        
        # Count stories created this month
        # CRITICAL: Add timeout to prevent 504 Gateway Timeout
        # If index is missing, query can take 60+ seconds and cause nginx timeout
        now = datetime.now()
        month_start = datetime(now.year, now.month, 1)
        
        stories_ref = db.collection("stories")
        query = stories_ref.where(filter=FieldFilter("owner_user_id", "==", user_id))\
                          .where(filter=FieldFilter("quota_counted", "==", True))\
                          .where(filter=FieldFilter("created_at", ">=", month_start.timestamp()))
        
        # CRITICAL: If index is missing, query will be slow (60+ seconds)
        # Check if query will fail due to missing index and return early
        # This prevents 504 Gateway Timeout from nginx
        try:
            # Try to get first result with limit(1) to check if query works
            # If it fails with index error, we know index is missing
            test_query = query.limit(1)
            list(test_query.stream())  # This will raise exception if index is missing
        except Exception as index_error:
            error_str = str(index_error)
            if "index" in error_str.lower() or "requires an index" in error_str.lower():
                print(f"⚠️ [check_user_quota] Index missing for quota query, allowing request to prevent 504 timeout")
                print(f"   Error: {error_str[:200]}")
                # Allow request if index is missing (prevents 504 timeout)
                # TODO: Create index at: https://console.firebase.google.com/v1/r/project/mino-mobile-app-firebase/firestore/databases/mino/indexes
                return True, 2  # Assume 1 story used, allow 2 more (conservative estimate)
            else:
                # Re-raise if it's a different error
                raise
        
        # Index exists, run full query (should be fast)
        print(f"🔍 [check_user_quota] Running quota query for user: {user_id}")
        print(f"   Query filters: owner_user_id={user_id}, quota_counted=True, created_at>={month_start.timestamp()}")
        story_count = len(list(query.stream()))
        quota_remaining = max(0, 3 - story_count)
        
        print(f"📊 [check_user_quota] Story count this month: {story_count}, quota remaining: {quota_remaining}")
        if quota_remaining == 0:
            print(f"❌ [check_user_quota] FREE USER QUOTA EXCEEDED: {story_count}/3 stories used this month")
        return quota_remaining > 0, quota_remaining
    except Exception as e:
        print(f"⚠️ Error checking quota: {e}")
        return True, 999  # Allow on error


async def check_user_entitlement(user_id: str) -> bool:
    """
    Check if user has active subscription (including grace period).
    
    BEST PRACTICE: Check Firestore only (fast, cached).
    RevenueCat webhooks and iOS app already update Firestore automatically.
    No need for RevenueCat API call - webhooks handle real-time updates.
    
    CRITICAL: Grace period support - if will_renew=True and subscription expired recently,
    user is in grace period (RevenueCat managed) and should have access.
    """
    if not db:
        print("⚠️ [check_user_entitlement] Firestore DB not initialized")
        return False
    
    try:
        subscription_ref = db.collection("subscriptions").document(user_id)
        subscription_doc = subscription_ref.get()
        
        if not subscription_doc.exists:
            print(f"ℹ️ [check_user_entitlement] No subscription found in Firestore for user: {user_id}")
            return False
        
        sub_data = subscription_doc.to_dict()
        expires_ms = sub_data.get("expires_date_ms")
        
        if not expires_ms:
            print(f"ℹ️ [check_user_entitlement] Subscription exists but no expiration date for user: {user_id}")
            return False
        
        expires_at = datetime.fromtimestamp(expires_ms / 1000, tz=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        will_renew = sub_data.get("will_renew", False)
        
        # Check if subscription is still active
        if expires_at > now_utc:
            print(f"✅ [check_user_entitlement] Active subscription found (expires: {expires_at})")
            return True
        
        # CRITICAL: Check grace period (RevenueCat managed)
        # If will_renew=True and subscription expired, user is in grace period (RevenueCat manages duration)
        # This matches check_user_quota logic exactly
        if will_renew and expires_at < now_utc:
            print(f"✅ [check_user_entitlement] User in GRACE PERIOD (expired: {expires_at}, will_renew: {will_renew})")
            return True
        
        # If will_renew is not set, check if subscription was updated recently (last 24 hours)
        # This handles cases where RevenueCat webhook hasn't updated will_renew yet
        if not will_renew and expires_at < now_utc:
            updated_at = sub_data.get("updated_at")
            if updated_at:
                # Firestore Timestamp to datetime (same logic as check_user_quota)
                if hasattr(updated_at, 'timestamp'):
                    updated_datetime = datetime.fromtimestamp(updated_at.timestamp())
                else:
                    updated_datetime = datetime.fromtimestamp(updated_at / 1000)
                
                hours_since_update = (now_utc.replace(tzinfo=None) - updated_datetime).total_seconds() / 3600
                
                # If subscription was updated recently (last 24 hours), assume it might renew
                if hours_since_update < 24:
                    print(f"✅ [check_user_entitlement] Subscription expired but updated recently ({hours_since_update:.1f}h ago) - assuming grace period")
                    return True
        
        print(f"ℹ️ [check_user_entitlement] Subscription expired (expired: {expires_at}, will_renew: {will_renew})")
        return False
            
    except Exception as e:
        print(f"⚠️ [check_user_entitlement] Error checking Firestore: {e}")
        return False


@app.post("/stories/custom", response_model=CreateStoryResponse)
async def create_custom_story(
    request: StoryRequest,
    user_id: Optional[str] = Depends(verify_firebase_token)
):
    """Create or retrieve a custom story.
    
    BEST PRACTICE: Deterministic story ID ensures idempotency
    - doc_id = story_{userId}_{character}_{topic}_{lang}
    - If doc exists with status in ("generating", "ready") → return same doc (no quota)
    - If doc doesn't exist or status="failed" → create new (quota deducted)
    
    This prevents:
    - Double requests → single story, single quota
    - Quota waste on retries
    - Race conditions in concurrent requests
    """
    print(f"🚀 [POST /stories/custom] ===== CUSTOM STORY REQUEST ======")
    print(f"   User ID: {user_id}")
    print(f"   Character ID: {request.character_id}")
    print(f"   Topic: {request.topic}")
    print(f"   Custom Description: {request.custom_description}")
    print(f"   Language: {request.language}")
    print(f"   Length: {request.length}")
    print(f"   Child Name: {request.child_name}")
    print(f"   =================================================")
    try:
        if not user_id:
            print("❌ [POST /stories/custom] No user_id - Authentication required")
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # CRITICAL: Validate topic and custom_description are meaningful (not random characters)
        # Reject requests with meaningless topics (e.g., "hkbvffhjkk", "asdf", etc.)
        topic_clean = request.topic.strip()
        if len(topic_clean) < 2:
            print(f"❌ [POST /stories/custom] Topic too short: '{topic_clean}'")
            raise HTTPException(status_code=400, detail="Topic must be at least 2 characters long")
        
        # Check if topic is just random characters (no vowels, no meaningful words)
        # MULTILINGUAL SUPPORT: Check for vowels in multiple languages
        # English vowels: aeiouy
        # Turkish vowels: aeiouıöü
        # Spanish/Portuguese vowels: aeiou
        # French vowels: aeiouy
        # Arabic: Check for Arabic script characters (Unicode range)
        # German vowels: aeiouäöü
        topic_lower = topic_clean.lower()
        vowels_english = set('aeiouy')
        vowels_turkish = set('aeiouıöü')
        vowels_spanish_portuguese = set('aeiou')
        vowels_french = set('aeiouy')
        vowels_german = set('aeiouäöü')
        
        # Check for Arabic script (Unicode range: \u0600-\u06FF)
        has_arabic = any('\u0600' <= c <= '\u06FF' for c in topic_clean)
        
        # Check for vowels in any supported language
        has_vowels = (
            any(c in vowels_english for c in topic_lower) or
            any(c in vowels_turkish for c in topic_lower) or
            any(c in vowels_spanish_portuguese for c in topic_lower) or
            any(c in vowels_french for c in topic_lower) or
            any(c in vowels_german for c in topic_lower) or
            has_arabic
        )
        
        # Allow short topics if they're common words (handled by topic mapping)
        # But reject if it's clearly random characters (e.g., "hkbvffhjkk")
        # For non-Latin scripts (like Arabic), allow if it contains script characters
        if not has_vowels and len(topic_clean) > 5:
            print(f"❌ [POST /stories/custom] Topic appears to be random characters: '{topic_clean}'")
            raise HTTPException(status_code=400, detail="Please provide a meaningful topic for your story")
        
        # Validate custom_description if provided
        if request.custom_description:
            desc_clean = request.custom_description.strip()
            if len(desc_clean) < 3:
                print(f"❌ [POST /stories/custom] Custom description too short: '{desc_clean}'")
                raise HTTPException(status_code=400, detail="Custom description must be at least 3 characters long")
            # Check if description is just random characters (multilingual support)
            desc_lower = desc_clean.lower()
            desc_has_arabic = any('\u0600' <= c <= '\u06FF' for c in desc_clean)
            desc_has_vowels = (
                any(c in vowels_english for c in desc_lower) or
                any(c in vowels_turkish for c in desc_lower) or
                any(c in vowels_spanish_portuguese for c in desc_lower) or
                any(c in vowels_french for c in desc_lower) or
                any(c in vowels_german for c in desc_lower) or
                desc_has_arabic
            )
            if not desc_has_vowels and len(desc_clean) > 5:
                print(f"❌ [POST /stories/custom] Custom description appears to be random characters: '{desc_clean}'")
                raise HTTPException(status_code=400, detail="Please provide a meaningful description for your story")
        
        # Generate deterministic story ID
        # CRITICAL: Include custom_description in ID to ensure different descriptions
        # create different stories, even if they map to the same topic
        story_id = generate_custom_story_id(
            user_id=user_id,
            character=request.character_id,
            topic=request.topic,
            lang=request.language,
            custom_description=request.custom_description
        )
        print(f"🔑 [POST /stories/custom] Deterministic story ID: {story_id}")
        
        # CRITICAL: Check if story already exists with status in ("generating", "ready")
        # If exists → return same doc (no quota, no overwrite, idempotent)
        # This is a feature, not a bug: prevents duplicate quota deduction and race conditions
        existing_story = await get_custom_story_by_id(story_id)
        if existing_story:
            existing_status = existing_story.get("status")
            existing_kind = existing_story.get("kind", "custom")
            
            # Only return if it's a custom story (safety check)
            if existing_kind == "custom" or existing_kind is None:
                if existing_status in ("text_pending", "generating_text", "audio_pending", "generating", "ready"):
                    print(f"✅ [POST /stories/custom] Found existing story: {story_id}")
                    print(f"   Status: {existing_status}, Kind: {existing_kind or 'custom (inferred)'}")
                    print(f"   Title: {existing_story.get('title', 'N/A')}")
                    print(f"   Scenes count: {len(existing_story.get('scenes', []))}")
                    
                    # Get current quota (no deduction for existing stories)
                    _, quota_remaining = await check_user_quota(user_id, request.length)
                    
                    # Return existing story (idempotent, no quota deduction)
                    response = CreateStoryResponse(
                        story_id=story_id,
                        status=existing_status,
                        quota_remaining=quota_remaining
                    )
                    print(f"📤 [POST /stories/custom] Returning existing story (idempotent, no quota)")
                    return response
                elif existing_status == "failed":
                    print(f"⚠️ [POST /stories/custom] Existing story has status='failed', will create new one")
                    # Continue to create new story below
                else:
                    print(f"ℹ️ [POST /stories/custom] Existing story has status='{existing_status}', will create new one")
                    # Continue to create new story below
            else:
                print(f"⚠️ [POST /stories/custom] Existing story is not custom (kind={existing_kind}), will create new one")
        
        # Story doesn't exist or has failed status → create new one
        print(f"📝 [POST /stories/custom] Creating new custom story: {story_id}")
        
        # CRITICAL: Check if user has another story in progress (text_pending or audio_pending)
        # Prevent creating new story while another is being generated
        if db:
            stories_ref = db.collection("stories")
            pending_query = stories_ref.where(filter=FieldFilter("owner_user_id", "==", user_id))\
                                      .where(filter=FieldFilter("status", "in", ["text_pending", "generating_text", "audio_pending", "generating"]))
            try:
                pending_stories = list(pending_query.stream())
                if pending_stories:
                    # Filter out the current story_id (if it exists with failed status)
                    other_pending = [s for s in pending_stories if s.id != story_id]
                    if other_pending:
                        pending_story_id = other_pending[0].id
                        pending_status = other_pending[0].to_dict().get("status", "unknown")
                        print(f"❌ [POST /stories/custom] User has another story in progress: {pending_story_id} (status: {pending_status})")
                        print(f"   Cannot create new story while another is being generated")
                        raise HTTPException(
                            status_code=409,  # Conflict
                            detail=f"Another story is currently being generated. Please wait for it to complete before creating a new one."
                        )
            except HTTPException:
                # Re-raise HTTPException (user-facing errors should not be caught)
                raise
            except Exception as e:
                print(f"⚠️ [POST /stories/custom] Error checking pending stories: {e}")
                # For non-HTTP exceptions (e.g., Firestore query errors), fail-open for better UX
                # But log the error so we can monitor and fix issues
                pass
        
        # Validate quota BEFORE creating (only for NEW stories)
        print(f"🔍 [POST /stories/custom] Checking quota for user: {user_id}, length: {request.length}")
        has_quota, quota_remaining = await check_user_quota(user_id, request.length)
        print(f"📊 [POST /stories/custom] Quota check result: has_quota={has_quota}, quota_remaining={quota_remaining}")
        if not has_quota:
            print(f"❌ [POST /stories/custom] Quota exceeded for user: {user_id}")
            raise HTTPException(
                status_code=403,
                detail=f"Quota exceeded. You've used your 3 free stories this month."
            )
        
        # BEST PRACTICE: Rate limiting for subscribers and trial users (fair use policy)
        # Free users already have quota limits (3/month), so rate limiting only applies to unlimited users
        if has_quota and quota_remaining == 999:  # Subscriber or Trial user (unlimited quota)
            rate_allowed, rate_reason = await check_rate_limit(user_id, is_subscriber=True)
            if not rate_allowed:
                print(f"⚠️ [POST /stories/custom] Rate limit exceeded for subscriber/trial user: {user_id}")
                raise HTTPException(
                    status_code=429,  # Too Many Requests
                    detail=f"Rate limit exceeded. {rate_reason}. Please wait before creating more stories."
                )
            print(f"✅ [POST /stories/custom] Rate limit check passed: {rate_reason}")
        
        # Validate length access
        if request.length == "dreamy":
            has_entitlement = await check_user_entitlement(user_id)
            if not has_entitlement:
                raise HTTPException(
                    status_code=403,
                    detail="Dreamy stories require a subscription"
                )
        
        # Normalize character and topic for storage
        character_slug = to_character_slug(request.character_id)
        
        # CRITICAL: For custom stories, don't map topic - use original
        # This ensures custom stories use the exact topic the parent provided
        if request.custom_description:
            topic_mapped = request.topic.lower().strip()  # Use original, no mapping
            topic_for_storage = request.topic.lower().strip()  # Store original topic
        else:
            topic_mapped = map_topic(request.topic.lower().strip())  # Map for system stories
            topic_for_storage = topic_mapped  # Store mapped topic
        
        # CONTROL 1: Store original request payload for traceability
        request_payload = {
            "character_id": request.character_id,  # Original from UI
            "character_slug": character_slug,  # Normalized
            "topic": request.topic,  # Original from UI
            "topic_mapped": topic_mapped,  # Canonical mapped (or original for custom)
            "language": request.language,
            "length": request.length,
            "child_name": request.child_name,
            "custom_description": request.custom_description
        }
        
        # Create Firestore document with status="text_pending"
        # BEST PRACTICE: Create safe, child-friendly title even if story might be rejected
        # This ensures rejected stories have appropriate titles
        safe_title = f"Story about {request.topic[:50]}"
        # For custom stories, use original topic for title; for system stories, use mapped topic if different
        if not request.custom_description and topic_mapped and topic_mapped != request.topic.lower():
            # Use mapped topic for title (e.g., "friendship" instead of "vurmamaya")
            safe_title = f"Story about {topic_mapped.replace('_', ' ').title()}"
        
        story_data = {
            "id": story_id,
            "title": safe_title,  # Safe title based on original or mapped topic
            "status": "text_pending",  # Will transition: text_pending → audio_pending → ready
            "character_id": character_slug,  # Store normalized character slug
            "language": request.language,
            "owner_user_id": user_id,
            # CRITICAL: topic is the product feature/program identifier (fixed key, not overridden)
            "topic": topic_for_storage,  # Store original for custom, mapped for system
            "topic_mapped": topic_mapped if request.custom_description else None,  # Reference only for custom
            "custom_description": request.custom_description,
            "child_name": request.child_name,
            "length_type": request.length,
            "kind": "custom",  # Always "custom" for user-generated stories
            "quota_counted": True,  # Mark quota as counted (will be deducted)
            "is_public": request.is_public,  # Whether story should be visible to other users (default: True)
            "request_payload": request_payload,  # CONTROL 1: Original request for traceability
            "created_at": time.time(),
            "updated_at": time.time()
        }
        
        if db:
            story_ref = db.collection("stories").document(story_id)
            story_ref.set(story_data)
            print(f"✅ [POST /stories/custom] Created Firestore document: {story_id}")
            print(f"   Character: {character_slug}, Topic: {topic_mapped}, Status: generating")
        
        # Enqueue generation job (async, non-blocking)
        import asyncio
        asyncio.create_task(generate_story_async(story_id, request))
        
        response = CreateStoryResponse(
            story_id=story_id,
            status="text_pending",  # Story is being generated
            quota_remaining=quota_remaining - 1  # Deduct quota for NEW story
        )
        
        # Log response for debugging
        print(f"📤 [POST /stories/custom] Returning response:")
        print(f"   story_id: {response.story_id}")
        print(f"   status: {response.status}")
        print(f"   quota_remaining: {response.quota_remaining} (quota deducted for new story)")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [POST /stories/custom] Error creating custom story: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


async def generate_story_async(story_id: str, request: StoryRequest):
    """Async task to generate story text, scenes, and audio."""
    try:
        # Update status to generating
        if db:
            story_ref = db.collection("stories").document(story_id)
            story_ref.update({"status": "generating_text"})
        
        # Generate story text using LLM
        # CRITICAL: Map length to target duration and token limits
        # quick = 2-3 minutes (~240-360 words at 120 wpm)
        # dreamy = 4-8 minutes (~480-960 words at 120 wpm)
        length_config = {
            "quick": {
                "duration_min": 1,  # 65-90 seconds target (1-1.5 minutes)
                "duration_max": 1.5,  # ~1.5 minutes max
                "target_words": 200,  # Minimum 200 words for 65-90 seconds at 120 wpm (200 words / 120 wpm ≈ 100 sec)
                # COST OPTIMIZATION: Start with conservative limit, retry with higher limit only if incomplete
                # This minimizes costs: most stories complete with 300 tokens, only incomplete ones retry with 400
                "max_tokens": 300,  # Initial limit (cost-optimized for 200+ words)
                "retry_max_tokens": 400  # Retry limit if incomplete (for languages with longer words)
            },
            "dreamy": {
                "duration_min": 3,
                "duration_max": 5,
                "target_words": 480,  # ~4 minutes at 120 wpm (3-5 min range)
                # COST OPTIMIZATION: Start with conservative limit, retry with higher limit only if incomplete
                # This minimizes costs: most stories complete with 700 tokens, only incomplete ones retry with 1000
                "max_tokens": 700,  # Initial limit (cost-optimized)
                "retry_max_tokens": 1000  # Retry limit if incomplete (for languages with longer words)
            }
        }
        config = length_config.get(request.length, length_config["quick"])
        
        # CRITICAL: Normalize character_id to slug (e.g., "spider fighter" → "spiderman")
        # This ensures correct character voice and audio files
        character_slug = to_character_slug(request.character_id)
        print(f"🔄 [generate_story_async] Character normalization:")
        print(f"   Original character_id: {request.character_id}")
        print(f"   Normalized slug: {character_slug}")
        
        # CRITICAL: Content moderation and fraud prevention with auto-correction
        # Step 1: Validate and sanitize input (multi-layer content moderation)
        # BEST PRACTICE: Auto-correction mode - automatically corrects low/medium severity issues
        print(f"🛡️ [generate_story_async] Starting content moderation with auto-correction...")
        sanitized_topic, sanitized_description, is_valid, moderation_result, auto_corrected_topic = await sanitize_and_validate_input(
            topic=request.topic,
            custom_description=request.custom_description,
            language=request.language,
            auto_correct=True  # Enable auto-correction for low/medium severity issues
        )
        
        if not is_valid:
            # Content rejected (high/critical severity) - mark story as failed with appropriate reason
            print(f"🚨 [generate_story_async] Content validation failed - rejecting story generation (high/critical severity)")
            if db:
                story_ref = db.collection("stories").document(story_id)
                
                # Create user-friendly rejection message based on moderation result
                rejection_reason = "Your story request contains content that is not appropriate for children. Please try a different topic that is positive and child-friendly."
                if moderation_result and moderation_result.get("flags"):
                    flags = moderation_result["flags"]
                    # Check if this is a false positive (negative behavior context)
                    if "violence_false_positive_ignored" in flags or "violence_review_needed" in flags:
                        # This shouldn't happen (should be allowed), but handle gracefully
                        rejection_reason = "We're having trouble understanding your request. Please try rephrasing it in a positive way (e.g., 'be kind to friends' instead of 'don't hit')."
                    elif "profanity" in flags:
                        rejection_reason = "Your story request contains inappropriate language. Please use positive, child-friendly words."
                    elif "inappropriate_theme" in flags:
                        rejection_reason = "Your story request contains themes that are not suitable for children. Please choose a positive, educational topic."
                    elif "spam" in flags:
                        rejection_reason = "Your story request appears to be spam. Please provide a valid story topic."
                    elif any("violence" in flag for flag in flags) and "violence_false_positive_ignored" not in flags:
                        # Check if this might be a false positive (negative behavior phrase)
                        if any(phrase in request.topic.lower() for phrase in ["vurmamaya", "tukurmemeye", "yapmamaya", "etmemeye", "durdurmaya", "bırakmaya"]):
                            rejection_reason = "We understand you want to encourage positive behavior. Please try rephrasing your request in a positive way (e.g., 'be gentle with friends' instead of 'don't hit friends')."
                        else:
                            rejection_reason = "Your story request contains content that is not safe for children. Please choose a positive, educational topic."
                    elif any("hate" in flag for flag in flags):
                        rejection_reason = "Your story request contains content that is not safe for children. Please choose a positive, educational topic."
                
                # Update title to be more appropriate for rejected stories
                # Use a safe, generic title instead of potentially inappropriate original topic
                safe_title = f"Story Request"
                
                story_ref.update({
                    "status": "rejected",
                    "rejection_reason": rejection_reason,
                    "title": safe_title,  # Update title to be safe and appropriate
                    "updated_at": time.time()
                })
            return  # Stop generation
        
        # Auto-correction was applied - log and inform user
        if auto_corrected_topic:
            print(f"🔄 [generate_story_async] Auto-correction applied: '{request.topic}' → '{auto_corrected_topic}'")
            print(f"   Original topic had minor issues, automatically corrected to safe alternative")
            # Store auto-correction info in Firestore for user transparency
            if db:
                story_ref = db.collection("stories").document(story_id)
                story_ref.update({
                    "original_topic": request.topic,  # Store original for reference
                    "auto_corrected": True,
                    "auto_corrected_topic": auto_corrected_topic,
                    "updated_at": time.time()
                })
        
        print(f"✅ [generate_story_async] Content validation passed (auto-corrected: {auto_corrected_topic is not None})")
        
        # Step 2: Pre-correct common spelling/grammar errors (after moderation)
        corrected_topic = correct_common_errors(sanitized_topic)
        if sanitized_description:
            corrected_description = correct_common_errors(sanitized_description)
            print(f"🔧 [generate_story_async] Corrected description: '{request.custom_description}' → '{corrected_description}'")
            full_topic_input = f"{corrected_topic} — Parent context: {corrected_description}"
        else:
            corrected_description = None
            full_topic_input = corrected_topic
        
        # Step 2: For custom stories, skip mapping - use original topic
        # CRITICAL: For custom stories, skip mapping - use original topic
        # This ensures "Tuğba ilacını içmiyor" generates a story about medicine, not nutrition
        if request.custom_description:
            # Custom story: use original topic (no mapping)
            mapped_topic = corrected_topic.lower().strip()
            print(f"🔍 [generate_story_async] Custom story - using original topic (no mapping): '{corrected_topic}'")
            # Custom story: use original topic directly, custom_description is already context
            prompt_topic = corrected_topic
        else:
            # System story: map topic to canonical
            # Try keyword-based mapping first (fast, deterministic)
            keyword_mapped_topic = map_topic(corrected_topic)
            print(f"🔍 [generate_story_async] Keyword-based mapping: '{corrected_topic}' → '{keyword_mapped_topic}'")
            
            # Step 3: If keyword mapping is uncertain (returned original), use AI to refine topic mapping
            # AI can better understand context and map free-form descriptions to canonical topics
            # Check if keyword mapping found a match (if it returns the original lowercase, it likely didn't find a match)
            # Also check if the mapped topic is in the canonical topics list
            canonical_topics = ["bedtime", "nutrition", "friendship", "confidence", "emotional_regulation",
                               "transitions", "kindness", "screen_time", "sharing", "sibling", "imagination"]
            keyword_mapping_found = keyword_mapped_topic in canonical_topics
            keyword_mapping_uncertain = not keyword_mapping_found  # Keyword mapping didn't find a canonical topic
            
            if keyword_mapping_uncertain:
                # Use AI to intelligently map the topic
                print(f"🤖 [generate_story_async] Using AI for topic mapping (keyword mapping uncertain)")
                ai_mapped_topic = await map_topic_with_ai(full_topic_input, request.language)
                if ai_mapped_topic:
                    print(f"🤖 [generate_story_async] AI mapping: '{full_topic_input}' → '{ai_mapped_topic}' (was: '{keyword_mapped_topic}')")
                    mapped_topic = ai_mapped_topic
                else:
                    print(f"⚠️ [generate_story_async] AI mapping failed, falling back to keyword-based: '{keyword_mapped_topic}'")
                    mapped_topic = keyword_mapped_topic if keyword_mapped_topic != corrected_topic.lower() else "bedtime"  # Safe fallback
            else:
                print(f"✅ [generate_story_async] Using keyword-based mapping: '{keyword_mapped_topic}'")
                mapped_topic = keyword_mapped_topic
        
        # Step 4: Use mapped topic for story generation
        prompt_topic = mapped_topic
        
        # CONTROL 2: Prepare debug request payload for prompt
        debug_request_payload = {
            "character_id_original": request.character_id,
            "character_slug_normalized": character_slug,
            "topic_original": request.topic,
            "topic_mapped": mapped_topic,
            "language": request.language,
            "length": request.length,
            "child_name": request.child_name,
            "custom_description": request.custom_description
        }
        
        # Generate story with OpenAI
        # COST OPTIMIZATION: Pass retry_max_tokens for cost-efficient retry
        retry_max_tokens = config.get("retry_max_tokens", int(config["max_tokens"] * 1.5))
        
        story_text = await generate_story_text(
            topic=prompt_topic,
            character=character_slug,  # Use normalized slug
            language=request.language,
            child_name=request.child_name,
            max_tokens=config["max_tokens"],
            custom_description=corrected_description,  # CRITICAL: Pass custom_description for behavior targeting
            retry_max_tokens=retry_max_tokens,  # Pass retry limit for cost optimization
            target_duration_min=config["duration_min"],
            target_duration_max=config["duration_max"],
            target_words=config["target_words"],
            story_length=request.length,  # Pass story length for structured format (quick vs dreamy)
            debug_request_payload=debug_request_payload  # CONTROL 2: For prompt verification
        )
        
        # BEST PRACTICE: Split text into scenes with videoKeys
        # This enables proper character animation during playback
        # Use normalized character slug for consistency
        scenes = split_text_into_scenes(
            text=story_text,
            character=character_slug,  # Use normalized slug
            language=request.language,
            child_name=request.child_name
        )
        
        # ✅ STORY CREATED
        print(f"✅ STORY CREATED: story_id={story_id}, character={character_slug}, topic={mapped_topic}, lang={request.language}, scenes={len(scenes)}")
        
        # CRITICAL: Validate generated story content (output moderation)
        print(f"🛡️ [generate_story_async] Validating generated story content...")
        story_moderation = await moderate_content(story_text, request.language)
        if not story_moderation["is_safe"]:
            print(f"🚨 [generate_story_async] Generated story failed moderation: {story_moderation['reason']}")
            # Regenerate with stricter prompt
            print(f"🔄 [generate_story_async] Regenerating story with stricter safety guidelines...")
            story_text = await generate_story_text(
                topic=prompt_topic,
                character=character_slug,
                language=request.language,
                child_name=request.child_name,
                max_tokens=config["max_tokens"],
                target_duration_min=config["duration_min"],
                target_duration_max=config["duration_max"],
                target_words=config["target_words"],
                story_length=request.length,  # Pass story length for structured format
                strict_safety=True  # Enable strict safety mode
            )
            # Re-validate
            story_moderation = await moderate_content(story_text, request.language)
            if not story_moderation["is_safe"]:
                # Still unsafe - mark as failed
                print(f"🚨 [generate_story_async] Story still unsafe after regeneration - marking as failed")
                if db:
                    story_ref = db.collection("stories").document(story_id)
                    # Create user-friendly failure message
                    failure_reason = "We couldn't generate a safe story for your request. Please try a different topic that is positive and child-friendly."
                    if story_moderation.get("flags"):
                        flags = story_moderation["flags"]
                        if any("violence" in flag or "hate" in flag for flag in flags):
                            failure_reason = "The generated story contained inappropriate content. Please try a different, more positive topic."
                    
                    story_ref.update({
                        "status": "failed",
                        "failure_reason": failure_reason,
                        "updated_at": time.time()
                    })
                return
        
        # Generate story title using AI (summarize story content into an engaging title)
        print(f"📝 [generate_story_async] Generating story title with AI...")
        # CRITICAL: For custom stories, use original topic for title generation
        # This ensures titles reflect the actual topic (e.g., "Tuğba ilacını içmiyor" not "nutrition")
        title_topic = corrected_topic if request.custom_description else mapped_topic
        story_title = await generate_story_title(
            story_text=story_text,
            language=request.language,
            character=character_slug,
            child_name=request.child_name,
            topic=title_topic  # Use original topic for custom stories, mapped for system stories
        )
        
        # CONTROL 3: Extract characters used in generated story (for verification)
        # Check if the requested character name appears in the story text
        # Use language-aware character display name mapping (shared with generate_story_text)
        lang_key = request.language[:2] if len(request.language) >= 2 else "en"
        # Import shared character mapping (same as generate_story_text)
        # For verification, we check all possible character name variations
        # IMPORTANT: Using ASO-safe derivative names (not original copyrighted names)
        character_display_maps_verification = {
            "tr": {
                "spiderman": "Örümcek Savaşçısı", "minion": "Sarı Arkadaş", "tweety": "Cıvıl Kuş",
                "spongebob": "Baloncuk", "elsa": "Buz Prensesi Elisa", "tom": "Sinsi Kedi Tom",
                "jerry": "Zeki Fare Jerry", "ninjaturtles": "Kabuk Kahramanlar", "koko": "Koko",
                "bugsbunny": "Komik Tavşan", "ironman": "Metal Kahraman", "peppapig": "Domuzcuk",
                "bluey": "Mavi Köpek", "pawpatrol": "Kurtarma Köpekleri", "moana": "Okyanus Hayalcisi",
                "mario": "Süper Zıplayan", "shrek": "Yeşil Dev", "pussinboots": "Çizmeli Kedi",
                "sid": "Buz Arkadaşı", "dora": "Macera Keşifçisi", "olaf": "Kardan Adam Arkadaşı",
                "pikachu": "Sarı Şimşek", "scoobydoo": "Gizemli Köpek", "winnie": "Winnie", "bunny": "Tavşan",
                "barbie": "Pinko", "tractor": "Trac", "mcqueen": "Racer", "hulk": "Hully"
            },
            "en": {
                "spiderman": "Spider Fighter", "minion": "Yellow Buddy", "tweety": "Chirpy Bird",
                "spongebob": "Bubble", "elsa": "Ice Princess Elisa", "tom": "Sneaky Tim",
                "jerry": "Clever Herry", "ninjaturtles": "Shell Heroes", "koko": "Koko",
                "bugsbunny": "Funny Bunny", "ironman": "Metal Hero", "peppapig": "Piggy",
                "bluey": "Blue Dog", "pawpatrol": "Rescue Dogs", "moana": "Ocean Dreamer",
                "mario": "Super Jumper", "shrek": "Green Giant", "pussinboots": "Boots Cat",
                "sid": "Frost Friend", "dora": "Adventure Explorer", "olaf": "Snowman Buddy",
                "pikachu": "Yellow Spark", "scoobydoo": "Mystery Pup", "winnie": "Winnie", "bunny": "Bunny",
                "barbie": "Pinko", "tractor": "Trac", "mcqueen": "Yarışçı", "hulk": "Hully"
            },
            "de": {
                "spiderman": "Spinnenkämpfer", "minion": "Gelber Freund", "tweety": "Zwitschervogel",
                "spongebob": "Blase", "elsa": "Eisprinzessin Elisa", "tom": "Schlaue Katze Tom",
                "jerry": "Clevere Maus Jerry", "ninjaturtles": "Schildhelden", "koko": "Koko",
                "bugsbunny": "Lustiger Hase", "ironman": "Metall Held", "peppapig": "Schweinchen",
                "bluey": "Blauer Hund", "pawpatrol": "Rettungshunde", "moana": "Ozean Träumer",
                "mario": "Super Springer", "shrek": "Grüner Riese", "pussinboots": "Stiefel Kater",
                "sid": "Frost Freund", "dora": "Abenteuer Entdecker", "olaf": "Schneemann Freund",
                "pikachu": "Gelber Funke", "scoobydoo": "Geheimnis Welpe", "winnie": "Winnie", "bunny": "Hase",
                "barbie": "Pinko", "tractor": "Trac", "mcqueen": "Racer", "hulk": "Hully"
            },
            "es": {
                "spiderman": "Luchador Araña", "minion": "Amigo Amarillo", "tweety": "Pájaro Gorjeador",
                "spongebob": "Burbuja", "elsa": "Princesa de Hielo Elisa", "tom": "Gato Astuto Tom",
                "jerry": "Ratón Inteligente Jerry", "ninjaturtles": "Héroes Caparazón", "koko": "Koko",
                "bugsbunny": "Conejo Divertido", "ironman": "Héroe de Metal", "peppapig": "Cerdito",
                "bluey": "Perro Azul", "pawpatrol": "Perros Rescatadores", "moana": "Soñadora del Océano",
                "mario": "Super Saltador", "shrek": "Gigante Verde", "pussinboots": "Gato Botas",
                "sid": "Amigo Helado", "dora": "Explorador Aventurero", "olaf": "Amigo Muñeco de Nieve",
                "pikachu": "Chispa Amarilla", "scoobydoo": "Cachorro Misterioso", "winnie": "Winnie", "bunny": "Conejo",
                "barbie": "Pinko", "tractor": "Trac", "mcqueen": "Racer", "hulk": "Hully"
            },
            "fr": {
                "spiderman": "Combattant Araignée", "minion": "Ami Jaune", "tweety": "Oiseau Gazouillant",
                "spongebob": "Bulle", "elsa": "Princesse des Glaces Elisa", "tom": "Chat Rusé Tom",
                "jerry": "Souris Maligne Jerry", "ninjaturtles": "Héros Carapace", "koko": "Koko",
                "bugsbunny": "Lapin Rigolo", "ironman": "Héros Métal", "peppapig": "Cochon",
                "bluey": "Chien Bleu", "pawpatrol": "Chiens Sauveteurs", "moana": "Rêveuse de l'Océan",
                "mario": "Super Sauteur", "shrek": "Géant Vert", "pussinboots": "Chat Bottes",
                "sid": "Ami Givré", "dora": "Explorateur Aventurier", "olaf": "Ami Bonhomme de Neige",
                "pikachu": "Étincelle Jaune", "scoobydoo": "Chiot Mystérieux", "winnie": "Winnie", "bunny": "Lapin",
                "barbie": "Pinko", "tractor": "Trac", "mcqueen": "Racer", "hulk": "Hully"
            },
            "pt": {
                "spiderman": "Lutador Aranha", "minion": "Amigo Amarelo", "tweety": "Pássaro Tagarela",
                "spongebob": "Bolha", "elsa": "Princesa do Gelo Elisa", "tom": "Gato Esperto Tom",
                "jerry": "Rato Inteligente Jerry", "ninjaturtles": "Heróis Casca", "koko": "Koko",
                "bugsbunny": "Coelho Engraçado", "ironman": "Herói de Metal", "peppapig": "Porquinho",
                "bluey": "Cachorro Azul", "pawpatrol": "Cães Resgatadores", "moana": "Sonhadora do Oceano",
                "mario": "Super Saltador", "shrek": "Gigante Verde", "pussinboots": "Gato de Botas",
                "sid": "Amigo Gelado", "dora": "Exploradora Aventureira", "olaf": "Amigo Boneco de Neve",
                "pikachu": "Faísca Amarela", "scoobydoo": "Cachorrinho Misterioso", "winnie": "Winnie", "bunny": "Coelho",
                "barbie": "Pinko", "tractor": "Trac", "mcqueen": "Racer", "hulk": "Hully"
            },
            "ar": {
                "spiderman": "مقاتل العنكبوت", "minion": "الصديق الأصفر", "tweety": "الطائر النشيط",
                "spongebob": "الفقاعة", "elsa": "أميرة الجليد إليزا", "tom": "القط الماكر توم",
                "jerry": "الفأر الذكي جيري", "ninjaturtles": "أبطال القوقعة", "koko": "Koko",
                "bugsbunny": "الأرنب المضحك", "ironman": "بطل المعدن", "peppapig": "الخنزير الصغير",
                "bluey": "الكلب الأزرق", "pawpatrol": "كلاب الإنقاذ", "moana": "حالمة المحيط",
                "mario": "القافز العظيم", "shrek": "العملاق الأخضر", "pussinboots": "القط ذو الأحذية",
                "sid": "صديق الصقيع", "dora": "المستكشفة المغامرة", "olaf": "صديق رجل الثلج",
                "pikachu": "الشرارة الصفراء", "scoobydoo": "الجرو الغامض", "winnie": "Winnie", "bunny": "الأرنب",
                "barbie": "Pinko", "tractor": "Trac", "mcqueen": "Racer", "hulk": "Hully"
            }
        }
        character_display_map = character_display_maps_verification.get(lang_key, character_display_maps_verification["en"])
        requested_character_name = character_display_map.get(character_slug, character_slug.capitalize())
        characters_used = []
        if requested_character_name.lower() in story_text.lower():
            characters_used.append(requested_character_name)
        # Also check for character slug
        if character_slug.lower() in story_text.lower():
            characters_used.append(character_slug)
        
        # Save text, scenes, and title to Firestore
        # CRITICAL: For custom stories, keep original topic in topic field
        # For system stories, use mapped topic for consistency
        if request.custom_description:
            # Custom story: keep original topic
            topic_for_firestore = corrected_topic.lower().strip()
        else:
            # System story: use mapped topic
            topic_for_firestore = mapped_topic
        # CRITICAL: Ensure all scenes have required fields for iOS decoding
        # - audio_url: None (so iOS can decode the field even if null)
        # - type: Must be present (iOS requires this field)
        # - videoKey: Must be present (iOS uses this for video asset loading)
        scenes_with_audio_url = []
        for scene in scenes:
            scene_copy = scene.copy()
            # Ensure audio_url field exists (null when pending, URL when ready)
            if "audio_url" not in scene_copy:
                scene_copy["audio_url"] = None
            # CRITICAL: Ensure type field exists (iOS requires this field)
            # split_text_into_scenes should always add type, but ensure it for backward compatibility
            if "type" not in scene_copy:
                # Infer type from scene id for backward compatibility
                scene_id = scene_copy.get("id", "")
                if "opening" in scene_id.lower():
                    scene_copy["type"] = "opening"
                elif "closure" in scene_id.lower():
                    scene_copy["type"] = "closure"
                else:
                    scene_copy["type"] = "speak"  # Default type (matches SceneType.speak enum)
                print(f"⚠️ [generate_story_async] Scene '{scene_id}' missing 'type' field, inferred: {scene_copy['type']}")
            # CRITICAL: Ensure videoKey field exists (iOS uses this for video asset loading)
            # BEST PRACTICE: Default to "talking" if missing (matches storage video files: {character}_talking_v1.mp4)
            if "videoKey" not in scene_copy or not scene_copy.get("videoKey"):
                scene_copy["videoKey"] = "talking"  # Default videoKey (most common for speak scenes)
                scene_id = scene_copy.get("id", "")
                print(f"⚠️ [generate_story_async] Scene '{scene_id}' missing 'videoKey' field, using default: 'talking'")
            scenes_with_audio_url.append(scene_copy)
        
        if db:
            story_ref = db.collection("stories").document(story_id)
            total_scenes = len(scenes_with_audio_url)
            story_ref.update({
                "text": story_text,
                "scenes": scenes_with_audio_url,  # Add scene structure with audio_url: None for pending scenes
                "title": story_title,  # AI-generated title
                "topic": topic_for_firestore,  # CRITICAL: Original for custom, mapped for system
                "kind": "custom",  # Ensure kind field is preserved (custom stories are always "custom")
                "status": "audio_pending",
                "audio_progress": {
                    "completed": 0,
                    "total": total_scenes
                },
                # CONTROL 3: Store generated text and characters used for verification
                # CRITICAL: Store both "text" (for UI) and "generated_text" (for backward compatibility)
                # UI expects "text" field, so we store it as "text" primarily
                "text": story_text,  # Full generated story text (UI expects this field)
                "generated_text": story_text,  # Also store as generated_text for backward compatibility
                "characters_used": characters_used,  # Characters actually used in story
                "updated_at": time.time()
            })
            print(f"📝 [generate_story_async] Updated topic field: '{request.topic}' → '{topic_for_firestore}'")
            print(f"📊 [generate_story_async] Initialized audio progress: 0/{total_scenes} scenes")
            print(f"📝 [generate_story_async] Story title generated: '{story_title}'")
        
        # Generate audio for each scene
        # BEST PRACTICE: Generate scene-by-scene audio for proper playback
        # This enables CallView to play audio per scene with proper character animation
        print(f"🎤 [generate_story_async] Generating scene-by-scene audio:")
        print(f"   Original character_id: {request.character_id}")
        print(f"   Normalized character_slug: {character_slug}")
        print(f"   language: {request.language}")
        print(f"   scenes count: {len(scenes)}")
        print(f"   ✅ Character-specific voice will be used for TTS generation (CHARACTER_VOICES lookup)")
        
        # Generate audio for each scene
        # BEST PRACTICE: Generate audio in parallel for faster completion
        # This reduces total waiting time from N*T to ~T (where N=scene count, T=avg generation time)
        total_scenes = len([s for s in scenes if s.get("text", "")])  # Count scenes with text
        
        async def generate_scene_audio(scene_index: int, scene: dict) -> tuple[int, str, float]:
            """Generate audio for a single scene and return (scene_index, audio_url, duration)."""
            scene_text = scene.get("text", "")
            if not scene_text:
                print(f"⚠️ [generate_story_async] Scene {scene_index} has no text, skipping audio generation")
                return (scene_index, None, 0.0)
            
            try:
                # Generate audio for this scene
                # CRITICAL: Character-specific voice settings
                # - character_slug (e.g., "mino", "bubu", "luna", "sunny") is passed to generate_tts
                # - generate_tts will look up CHARACTER_VOICES[character_slug] to get character-specific:
                #   * voice_id (unique ElevenLabs voice for each character)
                #   * emotion (character-specific emotion: calm, cheerful, sad, energetic, etc.)
                #   * speed (character-specific speed: 0.78-1.0)
                #   * pitch (character-specific pitch: 0.88-1.05)
                # This ensures each character uses their unique voice (e.g., Bubu's sad, soft voice vs. Luna's cheerful, bright voice)
                # - Pass story_id so that each custom story keeps its own unique audio files per scene.
                # CRITICAL: Use mapped_topic (not request.topic) for audio URL generation
                # This ensures audio URL matches the story's topic field in Firestore
                # Example: request.topic="kedilerle iyi geçinmek" → mapped_topic="friendship"
                # Audio URL should use "friendship", not "kedilerle iyi geçinmek"
                scene_audio_url = await generate_tts(
                    text=scene_text,
                    style={"stability": 0.7, "similarity_boost": 0.85, "style": 0.6},
                    lang=request.language,
                    character=character_slug,  # CRITICAL: Character slug for CHARACTER_VOICES lookup (character-specific voice)
                    topic=mapped_topic,  # Use mapped_topic, not request.topic
                    scene_index=scene_index,
                    story_id=story_id,
                )
                
                # Get scene audio duration
                scene_duration = await get_audio_duration(scene_audio_url)
                
                # Add audio URL to scene
                scene["audio_url"] = scene_audio_url
                
                # Update progress in Firestore (real-time progress tracking)
                # NOTE: In parallel generation, we update progress as each scene completes
                # This gives real-time feedback even though scenes are generated in parallel
                # We use a simple read-then-update approach (minor race condition possible but acceptable for progress tracking)
                if db:
                    story_ref = db.collection("stories").document(story_id)
                    try:
                        story_doc = story_ref.get()
                        if story_doc.exists:
                            # FIX: Use to_dict() to get document data, then use Python dict.get() for default value
                            story_data = story_doc.to_dict()
                            current_progress = story_data.get("audio_progress", {}) if story_data else {}
                            current_completed = current_progress.get("completed", 0) if isinstance(current_progress, dict) else 0
                            new_completed = current_completed + 1
                            
                            story_ref.update({
                                "audio_progress": {
                                    "completed": new_completed,
                                    "total": total_scenes
                                },
                                "updated_at": time.time()
                            })
                            print(f"📊 [generate_story_async] Progress updated: {new_completed}/{total_scenes} scenes completed ({int(new_completed/total_scenes*100)}%)")
                    except Exception as e:
                        print(f"⚠️ [generate_story_async] Failed to update progress: {e}")
                
                print(f"✅ [generate_story_async] Scene {scene_index} audio generated: {scene_audio_url} ({scene_duration}s)")
                return (scene_index, scene_audio_url, scene_duration)
            except Exception as e:
                print(f"❌ [generate_story_async] Error generating audio for scene {scene_index}: {e}")
                return (scene_index, None, 0.0)
        
        # Generate all scene audio in parallel (up to 3 concurrent to avoid rate limiting)
        import asyncio
        scene_tasks = []
        for scene_index, scene in enumerate(scenes):
            if scene.get("text", ""):
                scene_tasks.append(generate_scene_audio(scene_index, scene))
        
        # Process in batches of 3 to avoid overwhelming TTS API
        scene_audios = []
        total_duration = 0.0
        batch_size = 3
        for i in range(0, len(scene_tasks), batch_size):
            batch = scene_tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch)
            for scene_index, audio_url, duration in batch_results:
                if audio_url:
                    scene_audios.append(audio_url)
                    total_duration += duration
        
        # Use first scene audio as main audio_url (for backward compatibility)
        main_audio_url = scene_audios[0] if scene_audios else None
        
        # Update story with scene audio URLs and main audio URL
        # CRITICAL: Mark as ready only after ALL scenes have audio URLs
        if db:
            story_ref = db.collection("stories").document(story_id)
            completed_count = len(scene_audios)
            
            # Debug: Verify scenes have audio_url before saving
            print(f"🔍 [generate_story_async] Verifying scenes before saving to Firestore:")
            for i, scene in enumerate(scenes):
                if isinstance(scene, dict):
                    has_audio = "audio_url" in scene and scene.get("audio_url") is not None
                    print(f"   Scene {i} (id={scene.get('id', 'N/A')}): audio_url={'✅ ' + scene.get('audio_url', 'N/A') if has_audio else '❌ MISSING'}")
                else:
                    print(f"   Scene {i}: Not a dict (type={type(scene)})")
            
            update_data = {
                "scenes": scenes,  # Update scenes with audio_url for each scene
                "status": "ready",
                "audio_progress": {
                    "completed": completed_count,
                    "total": total_scenes
                },
                "quota_counted": True,
                "updated_at": time.time()
            }
            
            # Add main audio_url for backward compatibility
            if main_audio_url:
                update_data["audio_url"] = main_audio_url
                update_data["duration_seconds"] = total_duration
            
            story_ref.update(update_data)
            print(f"📊 [generate_story_async] Final progress: {completed_count}/{total_scenes} scenes completed (100%)")
            
            # ✅ AUDIO FILES CREATED
            print(f"✅ AUDIO FILES CREATED: story_id={story_id}, character={character_slug}, total_scenes={total_scenes}, total_duration={int(total_duration)}s")
        
        # BEST PRACTICE: Also save story to local storage for compatibility with /story/{character}/{topic} endpoint
        # This enables the endpoint to find user-generated stories in local storage as well
        # NOTE: We save with standard topic name (not story_id) so endpoint can find it
        # If multiple users create stories with same topic, the most recent one will be used
        # This is acceptable because:
        # 1. Firestore query (priority 1) will return user-specific story if user_id is provided
        # 2. Local storage is fallback for public/pre-generated stories
        try:
            # NOTE: to_character_slug and content_story_path are already imported at the top of the file
            # character_slug is already normalized above (line 2472)
            topic_mapped_for_file = mapped_topic  # Use the mapped topic (e.g., "bedtime" not "bedtime story")
            
            # Extract user_id from story_id: story_{user_id}_{timestamp}
            user_id_from_story = story_id.split("_")[1] if "_" in story_id else None
            
            # Use standard topic name for filename (same as pre-generated stories)
            # This allows endpoint to find it via /story/{character}/{topic}
            story_path = content_story_path(request.language, character_slug, topic_mapped_for_file)
            
            # Ensure directory exists
            story_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Prepare story data in local storage format (compatible with pre-generated stories)
            local_story_data = {
                "topic": topic_mapped_for_file,
                "character": character_slug,  # Use already normalized character_slug
                "title": story_title,
                "text": story_text,
                "scenes": scenes,  # Already includes audio_url for each scene
                "durationMinutes": int(total_duration / 60) if total_duration > 0 else config["duration_min"],
                "language": request.language,
                "story_id": story_id,  # Keep story_id for reference
                "owner_user_id": user_id_from_story  # Extract from story_id
            }
            
            # Save to local storage (overwrites if exists - most recent story wins)
            with open(story_path, "w", encoding="utf-8") as f:
                json.dump(local_story_data, f, ensure_ascii=False, indent=2)
            
            print(f"💾 [generate_story_async] Story also saved to local storage: {story_path}")
            print(f"   File: {topic_mapped_for_file}.json")
            print(f"   This enables /story/{character_slug}/{topic_mapped_for_file} endpoint to find it")
            print(f"   NOTE: If multiple users create same topic, most recent story will be in local storage")
            print(f"   But Firestore query (priority 1) will return user-specific story if user_id is provided")
        except Exception as e:
            print(f"⚠️ [generate_story_async] Failed to save story to local storage: {e}")
            # Non-critical error - story is already in Firestore
            import traceback
            traceback.print_exc()
        
        print(f"✅ Story {story_id} generated successfully - All {completed_count} audio files completed")
        
        # ✅ READY
        print(f"✅ READY: story_id={story_id}, character={character_slug}, topic={mapped_topic}, status=ready, audio_files={completed_count}/{total_scenes}")
        
    except Exception as e:
        print(f"❌ Error generating story {story_id}: {e}")
        import traceback
        traceback.print_exc()
        
        # Mark as failed with user-friendly error message
        if db:
            story_ref = db.collection("stories").document(story_id)
            # Create user-friendly failure message
            error_str = str(e)
            if "scenes" in error_str.lower() or "unboundlocalerror" in error_str.lower():
                failure_reason = "An internal error occurred while generating the story. Please try again."
            elif "timeout" in error_str.lower():
                failure_reason = "The story generation took too long. Please try again with a shorter story length."
            elif "quota" in error_str.lower() or "limit" in error_str.lower():
                failure_reason = "Story generation limit reached. Please try again later or upgrade your plan."
            else:
                failure_reason = "An error occurred while generating the story. Please try again with a different topic."
            
            story_ref.update({
                "status": "failed",
                "failure_reason": failure_reason,
                "updated_at": time.time()
            })


async def generate_story_text(
    topic: str,
    character: str,
    language: str,
    child_name: Optional[str],
    max_tokens: int,
    custom_description: Optional[str] = None,  # CRITICAL: Custom description for behavior targeting
    retry_max_tokens: Optional[int] = None,  # COST OPTIMIZATION: Retry limit if story incomplete
    target_duration_min: int = 2,
    target_duration_max: int = 3,
    target_words: int = 300,
    story_length: str = "quick",  # Story length: "quick" or "dreamy" (for structured format)
    strict_safety: bool = False,
    debug_request_payload: Optional[dict] = None  # CONTROL 2: For prompt verification
) -> str:
    """Generate story text using OpenAI with target duration.
    
    Args:
        topic: Story topic
        character: Character slug (e.g., "spiderman", "minion")
        language: Language code
        child_name: Optional child name
        max_tokens: Maximum tokens for generation
        target_duration_min: Target minimum duration in minutes
        target_duration_max: Target maximum duration in minutes
        target_words: Target word count (for prompt guidance)
    """
    if not settings.OPENAI_API_KEY:
        # Fallback story
        return f"Once upon a time, {character} told a wonderful story about {topic}."
    
    import openai
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    
    # Map character slug to display name (language-aware for prompt)
    lang_key = language[:2] if len(language) >= 2 else "en"
    
    # Language-specific character display names (shared with generate_story_title)
    # CRITICAL: All characters must be present for consistency between UI and Backend
    # Age-appropriate translations for 2-8 year olds: FUNNY, REALISTIC, SHORT
    # IMPORTANT: Using ASO-safe derivative names (not original copyrighted names)
    character_display_maps = {
        "tr": {
            "spiderman": "Örümcek Savaşçısı",
            "minion": "Sarı Arkadaş",
            "tweety": "Cıvıl Kuş",
            "spongebob": "Baloncuk",
            "elsa": "Buz Prensesi Elisa",
            "tom": "Sinsi Kedi Tim",
            "jerry": "Zeki Fare Herry",
            "ninjaturtles": "Kabuk Kahramanlar",
            "sunny": "Sunny",
            "bubu": "Bubu",
            "luna": "Luna",
            "tiko": "Tiko",
            "mino": "Mino",
            "koko": "Koko",
            "bugsbunny": "Komik Tavşan",
            "ironman": "Metal Kahraman",
            "peppapig": "Domuzcuk",
            "bluey": "Mavi Köpek",
            "pawpatrol": "Kurtarma Köpekleri",
            "moana": "Okyanus Hayalcisi",
            "mario": "Süper Zıplayan",
            "shrek": "Yeşil Dev",
            "pussinboots": "Çizmeli Kedi",
            "sid": "Buz Arkadaşı",
            "dora": "Macera Keşifçisi",
            "olaf": "Kardan Adam Arkadaşı",
            "pikachu": "Sarı Şimşek",
            "scoobydoo": "Gizemli Köpek",
            "winnie": "Winnie",
            "bunny": "Tavşan",
            "barbie": "Pinko",
            "tractor": "Trac",
            "mcqueen": "Yarışçı",
            "hulk": "Hully"
        },
        "en": {
            "spiderman": "Spider Fighter",
            "minion": "Yellow Buddy",
            "tweety": "Chirpy Bird",
            "spongebob": "Bubble",
            "elsa": "Ice Princess Elisa",
            "tom": "Sneaky Tim",
            "jerry": "Clever Herry",
            "ninjaturtles": "Shell Heroes",
            "sunny": "Sunny",
            "bubu": "Bubu",
            "luna": "Luna",
            "tiko": "Tiko",
            "mino": "Mino",
            "koko": "Koko",
            "bugsbunny": "Funny Bunny",
            "ironman": "Metal Hero",
            "peppapig": "Piggy",
            "bluey": "Blue Dog",
            "pawpatrol": "Rescue Dogs",
            "moana": "Ocean Dreamer",
            "mario": "Super Jumper",
            "shrek": "Green Giant",
            "pussinboots": "Boots Cat",
            "sid": "Frost Friend",
            "dora": "Adventure Explorer",
            "olaf": "Snowman Buddy",
            "pikachu": "Yellow Spark",
            "scoobydoo": "Mystery Pup",
            "winnie": "Winnie",
            "bunny": "Bunny",
            "barbie": "Pinko",
            "tractor": "Trac",
            "mcqueen": "Racer",
            "hulk": "Hully"
        },
        "de": {
            "spiderman": "Spinnenkämpfer",
            "minion": "Gelber Freund",
            "tweety": "Zwitschervogel",
            "spongebob": "Blase",
            "elsa": "Eisprinzessin Elisa",
            "tom": "Schlaue Katze Tom",
            "jerry": "Clevere Maus Jerry",
            "ninjaturtles": "Schildhelden",
            "sunny": "Sunny",
            "bubu": "Bubu",
            "luna": "Luna",
            "tiko": "Tiko",
            "mino": "Mino",
            "koko": "Koko",
            "bugsbunny": "Lustiger Hase",
            "ironman": "Metall Held",
            "peppapig": "Schweinchen",
            "bluey": "Blauer Hund",
            "pawpatrol": "Rettungshunde",
            "moana": "Ozean Träumer",
            "mario": "Super Springer",
            "shrek": "Grüner Riese",
            "pussinboots": "Stiefel Kater",
            "sid": "Frost Freund",
            "dora": "Abenteuer Entdecker",
            "olaf": "Schneemann Freund",
            "pikachu": "Gelber Funke",
            "scoobydoo": "Geheimnis Welpe",
            "winnie": "Winnie",
            "bunny": "Hase",
            "barbie": "Pinko",
            "tractor": "Trac",
            "mcqueen": "Racer",
            "hulk": "Hully"
        },
        "es": {
            "spiderman": "Luchador Araña",
            "minion": "Amigo Amarillo",
            "tweety": "Pájaro Gorjeador",
            "spongebob": "Burbuja",
            "elsa": "Princesa de Hielo Elisa",
            "tom": "Gato Astuto Tom",
            "jerry": "Ratón Inteligente Jerry",
            "ninjaturtles": "Héroes Caparazón",
            "sunny": "Sunny",
            "bubu": "Bubu",
            "luna": "Luna",
            "tiko": "Tiko",
            "mino": "Mino",
            "koko": "Koko",
            "bugsbunny": "Conejo Divertido",
            "ironman": "Héroe de Metal",
            "peppapig": "Cerdito",
            "bluey": "Perro Azul",
            "pawpatrol": "Perros Rescatadores",
            "moana": "Soñadora del Océano",
            "mario": "Super Saltador",
            "shrek": "Gigante Verde",
            "pussinboots": "Gato Botas",
            "sid": "Amigo Helado",
            "dora": "Explorador Aventurero",
            "olaf": "Amigo Muñeco de Nieve",
            "pikachu": "Chispa Amarilla",
            "scoobydoo": "Cachorro Misterioso",
            "winnie": "Winnie",
            "bunny": "Conejo",
            "barbie": "Pinko",
            "tractor": "Trac",
            "mcqueen": "Racer",
            "hulk": "Hully"
        },
        "fr": {
            "spiderman": "Combattant Araignée",
            "minion": "Ami Jaune",
            "tweety": "Oiseau Gazouillant",
            "spongebob": "Bulle",
            "elsa": "Princesse des Glaces Elisa",
            "tom": "Chat Rusé Tom",
            "jerry": "Souris Maligne Jerry",
            "ninjaturtles": "Héros Carapace",
            "sunny": "Sunny",
            "bubu": "Bubu",
            "luna": "Luna",
            "tiko": "Tiko",
            "mino": "Mino",
            "koko": "Koko",
            "bugsbunny": "Lapin Rigolo",
            "ironman": "Héros Métal",
            "peppapig": "Cochon",
            "bluey": "Chien Bleu",
            "pawpatrol": "Chiens Sauveteurs",
            "moana": "Rêveuse de l'Océan",
            "mario": "Super Sauteur",
            "shrek": "Géant Vert",
            "pussinboots": "Chat Bottes",
            "sid": "Ami Givré",
            "dora": "Explorateur Aventurier",
            "olaf": "Ami Bonhomme de Neige",
            "pikachu": "Étincelle Jaune",
            "scoobydoo": "Chiot Mystérieux",
            "winnie": "Winnie",
            "bunny": "Lapin",
            "barbie": "Pinko",
            "tractor": "Trac",
            "mcqueen": "Racer",
            "hulk": "Hully"
        },
        "pt": {
            "spiderman": "Lutador Aranha",
            "minion": "Amigo Amarelo",
            "tweety": "Pássaro Tagarela",
            "spongebob": "Bolha",
            "elsa": "Princesa do Gelo Elisa",
            "tom": "Gato Esperto Tom",
            "jerry": "Rato Inteligente Jerry",
            "ninjaturtles": "Heróis Casca",
            "sunny": "Sunny",
            "bubu": "Bubu",
            "luna": "Luna",
            "tiko": "Tiko",
            "mino": "Mino",
            "koko": "Koko",
            "bugsbunny": "Coelho Engraçado",
            "ironman": "Herói de Metal",
            "peppapig": "Porquinho",
            "bluey": "Cachorro Azul",
            "pawpatrol": "Cães Resgatadores",
            "moana": "Sonhadora do Oceano",
            "mario": "Super Saltador",
            "shrek": "Gigante Verde",
            "pussinboots": "Gato de Botas",
            "sid": "Amigo Gelado",
            "dora": "Exploradora Aventureira",
            "olaf": "Amigo Boneco de Neve",
            "pikachu": "Faísca Amarela",
            "scoobydoo": "Cachorrinho Misterioso",
            "winnie": "Winnie",
            "bunny": "Coelho",
            "barbie": "Pinko",
            "tractor": "Trac",
            "mcqueen": "Racer",
            "hulk": "Hully"
        },
        "ar": {
            "spiderman": "مقاتل العنكبوت",
            "minion": "الصديق الأصفر",
            "tweety": "الطائر النشيط",
            "spongebob": "الفقاعة",
            "elsa": "أميرة الجليد إليزا",
            "tom": "القط الماكر توم",
            "jerry": "الفأر الذكي جيري",
            "ninjaturtles": "أبطال القوقعة",
            "sunny": "Sunny",
            "bubu": "Bubu",
            "luna": "Luna",
            "tiko": "Tiko",
            "mino": "Mino",
            "koko": "Koko",
            "bugsbunny": "الأرنب المضحك",
            "ironman": "بطل المعدن",
            "peppapig": "الخنزير الصغير",
            "bluey": "الكلب الأزرق",
            "pawpatrol": "كلاب الإنقاذ",
            "moana": "حالمة المحيط",
            "mario": "القافز العظيم",
            "shrek": "العملاق الأخضر",
            "pussinboots": "القط ذو الأحذية",
            "sid": "صديق الصقيع",
            "dora": "المستكشفة المغامرة",
            "olaf": "صديق رجل الثلج",
            "pikachu": "الشرارة الصفراء",
            "scoobydoo": "الجرو الغامض",
            "winnie": "Winnie",
            "bunny": "الأرنب",
            "barbie": "Pinko",
            "tractor": "Trac",
            "mcqueen": "Racer",
            "hulk": "Hully"
        }
    }
    
    character_slug = character.lower()
    character_display_map = character_display_maps.get(lang_key, character_display_maps["en"])
    character_name = character_display_map.get(character_slug, character.capitalize())
    
    # Character-specific persona descriptions (kept short and reusable across topics)
    character_personas = {
        "mino": (
            "Mino is a curious space explorer from a gentle, pastel-colored galaxy. "
            "Mino speaks softly, uses simple sentences, and always helps children feel safe at bedtime."
        ),
        "luna": (
            "Luna is a calm moon fairy who helps children understand and name their feelings. "
            "She talks slowly, validates emotions, and offers gentle coping ideas."
        ),
        "tiko": (
            "Tiko is a playful fox who loves games and movement. "
            "He turns everyday challenges into small adventures and uses humor to keep things light."
        ),
        "bubu": (
            "Bubu is a warm-hearted bear who teaches about friendship and sharing. "
            "She uses cozy, cuddly imagery and focuses on kindness between siblings and friends."
        ),
        "sunny": (
            "Sunny is a bright, optimistic character who boosts children's confidence. "
            "Sunny celebrates small wins and encourages brave, positive choices."
        ),
        "tom": (
            "Sneaky Tim is a curious, slightly mischievous cat who learns to make good choices. "
            "His stories often turn small everyday problems into funny, safe learning moments."
        ),
        "jerry": (
            "Clever Herry is thoughtful and observant. "
            "He helps children find smart, gentle solutions to their worries."
        ),
        "ninjaturtles": (
            "Shell Heroes Crew are brave, team-minded ninja turtles who support each other. "
            "They use teamwork, courage and playful action to help children feel strong, especially around school and social challenges."
        ),
        "spiderman": (
            "Spider Fighter is a friendly neighborhood hero. "
            "He talks about responsibility, bravery and doing the right thing, in a calm and reassuring way."
        ),
        "minion": (
            "Yellow Buddy is a silly, loving helper who adds gentle humor without being too loud. "
            "He turns chores and routines into light-hearted games."
        ),
        "elsa": (
            "Elisa the Ice Fairy is calm and magical. "
            "She uses snow, ice and sparkle imagery to create soothing, dreamy bedtime scenes."
        ),
        "spongebob": (
            "Bubble Buddy is fun and imaginative. "
            "He loves turning normal situations into undersea adventures, staying kind and non-scary."
        ),
        "tweety": (
            "Chirpy Birdie is a small, gentle bird who notices tiny details. "
            "She speaks softly and helps children feel heard and understood."
        )
    }
    persona = character_personas.get(character_slug, (
        f"{character_name} is a kind, gentle character who tells age-appropriate stories to children."
    ))
    
    child_part = f" named {child_name}" if child_name else ""
    # Language-specific child name examples
    child_name_examples = {
        "tr": f'"Merhaba {child_name}!" or "{child_name}, bugün sana..."',
        "en": f'"Hello {child_name}!" or "{child_name}, today I want to tell you..."',
        "de": f'"Hallo {child_name}!" or "{child_name}, heute möchte ich dir..."',
        "es": f'"¡Hola {child_name}!" or "{child_name}, hoy quiero contarte..."',
        "fr": f'"Bonjour {child_name}!" or "{child_name}, aujourd\'hui je veux te raconter..."',
        "pt": f'"Olá {child_name}!" or "{child_name}, hoje eu quero te contar..."',
        "ar": f'"مرحباً {child_name}!" or "{child_name}، اليوم أريد أن أخبرك..."'
    }
    lang_key = language[:2] if len(language) >= 2 else "en"
    child_name_example = child_name_examples.get(lang_key, child_name_examples["en"])
    
    # CRITICAL: Translate topic to target language for prompt
    # This ensures canonical topics like "bedtime" appear in the correct language (e.g., "uyku" in Turkish)
    topic_translations = {
        "tr": {
            "sharing": "paylaşma", "friendship": "arkadaşlık", "bedtime": "uyku", "confidence": "özgüven",
            "emotional_regulation": "duygusal düzenleme", "screen_time": "ekran süresi", "sibling": "kardeş",
            "imagination": "hayal gücü", "transitions": "geçiş", "kindness": "nezaket", "nutrition": "beslenme"
        },
        "en": {
            "sharing": "sharing", "friendship": "friendship", "bedtime": "bedtime", "confidence": "confidence",
            "emotional_regulation": "emotional regulation", "screen_time": "screen time", "sibling": "sibling",
            "imagination": "imagination", "transitions": "transitions", "kindness": "kindness", "nutrition": "nutrition"
        },
        "de": {
            "sharing": "teilen", "friendship": "freundschaft", "bedtime": "schlafenszeit", "confidence": "vertrauen",
            "emotional_regulation": "emotionale regulation", "screen_time": "bildschirmzeit", "sibling": "geschwister",
            "imagination": "fantasie", "transitions": "übergang", "kindness": "freundlichkeit", "nutrition": "ernährung"
        },
        "es": {
            "sharing": "compartir", "friendship": "amistad", "bedtime": "hora de dormir", "confidence": "confianza",
            "emotional_regulation": "regulación emocional", "screen_time": "tiempo de pantalla", "sibling": "hermano",
            "imagination": "imaginación", "transitions": "transición", "kindness": "bondad", "nutrition": "nutrición"
        },
        "fr": {
            "sharing": "partage", "friendship": "amitié", "bedtime": "coucher", "confidence": "confiance",
            "emotional_regulation": "régulation émotionnelle", "screen_time": "temps d'écran", "sibling": "frère",
            "imagination": "imagination", "transitions": "transition", "kindness": "gentillesse", "nutrition": "nutrition"
        },
        "pt": {
            "sharing": "compartilhar", "friendship": "amizade", "bedtime": "hora de dormir", "confidence": "confiança",
            "emotional_regulation": "regulação emocional", "screen_time": "tempo de tela", "sibling": "irmão",
            "imagination": "imaginação", "transitions": "transição", "kindness": "bondade", "nutrition": "nutrição"
        },
        "ar": {
            "sharing": "المشاركة", "friendship": "الصداقة", "bedtime": "وقت النوم", "confidence": "الثقة",
            "emotional_regulation": "التحكم العاطفي", "screen_time": "وقت الشاشة", "sibling": "الأخ",
            "imagination": "الخيال", "transitions": "الانتقال", "kindness": "اللطف", "nutrition": "التغذية"
        }
    }
    topic_map = topic_translations.get(lang_key, topic_translations["en"])
    
    # Extract canonical topic from topic string (may contain " — Parent context: ...")
    topic_base = topic.split(" — ")[0].strip().lower()
    
    # Check if topic_base is already in the target language (e.g., "uyku" in Turkish)
    # If it's already translated, use it as-is; otherwise translate from English canonical topic
    topic_translated = topic_map.get(topic_base, topic_base)
    
    # If topic contains custom description, preserve it but translate the base topic
    if " — " in topic:
        custom_part = topic.split(" — ", 1)[1]
        topic_for_prompt = f"{topic_translated} — {custom_part}"
    else:
        topic_for_prompt = topic_translated
    
    print(f"🌍 [generate_story_text] Topic translation: '{topic_base}' → '{topic_translated}' (lang: {lang_key})")
    
    # Language-specific generic terms of endearment (when child_name is not provided)
    generic_endearments = {
        "tr": '"küçük dostum", "canım", "tatlım", "güzel çocuk"',
        "en": '"little friend", "dear", "sweetheart", "buddy"',
        "de": '"kleiner Freund", "Schatz", "Liebling", "mein Kind"',
        "es": '"pequeño amigo", "cariño", "tesoro", "mi niño/niña"',
        "fr": '"petit ami", "mon chéri", "trésor", "mon enfant"',
        "pt": '"pequeno amigo", "querido", "querida", "meu filho/minha filha"',
        "ar": '"صديقي الصغير", "عزيزي", "عزيزتي", "ابني/ابنتي"'
    }
    generic_terms = generic_endearments.get(lang_key, generic_endearments["en"])
    
    if child_name:
        child_name_instruction = f"""
6. CRITICAL - CHILD NAME PERSONALIZATION: The story is for a child named {child_name}. You MUST use the child's name ({child_name}) multiple times throughout the story when addressing the child or referring to them. Use the child's name naturally in dialogue and narration, for example: {child_name_example}. The child's name should appear at least 3-5 times in the story."""
    else:
        child_name_instruction = f"""
6. CRITICAL - AFFECTIONATE ADDRESSING: Since no specific child name is provided, use warm, affectionate terms when addressing the child throughout the story. Use terms like {generic_terms} naturally and lovingly. These terms should appear multiple times (3-5 times) to create a personal, caring connection with the listener."""
    
    # Calculate target word count based on duration (120 words per minute for kid-friendly pace)
    target_word_count = target_words
    
    # PEDAGOGICAL APPROACH: All stories use evidence-based child development techniques
    # Based on: Positive Discipline, Montessori, Social-Emotional Learning (SEL), and Play Therapy principles
    pedagogical_instruction = """
7. CRITICAL - PEDAGOGICALLY APPROVED STORYTELLING APPROACH:
   Use these evidence-based child development techniques in ALL stories:
   
   a) POSITIVE MODELING (Social Learning Theory - Bandura):
      - Show characters making positive choices and experiencing natural positive outcomes
      - Never lecture, command, or tell the child what to do
      - Let the story character discover benefits through their own experience
   
   b) EMOTIONAL VALIDATION (Play Therapy principles):
      - Acknowledge that feelings are normal and okay
      - Show characters having similar feelings and working through them
      - Use phrases like "It's okay to feel..." or "Sometimes we all feel..."
   
   c) AUTONOMY SUPPORT (Self-Determination Theory):
      - Respect the child's ability to make their own choices
      - Present options, not commands
      - Focus on internal motivation, not external pressure
   
   d) NATURAL CONSEQUENCES (Positive Discipline):
      - Show logical, natural outcomes of actions in the story
      - Avoid threats, bribes, or fear-based motivation
      - Let characters learn through gentle experience
   
   e) CONNECTION BEFORE CORRECTION (Attachment Theory):
      - Build warmth and trust first
      - Make the child feel understood and accepted
      - The character is a supportive friend, not an authority figure
   
   NEVER USE:
   - Direct commands ("You should...", "You must...", "You need to...")
   - Guilt or shame ("Good children do...", "Don't be bad...")
   - Comparisons ("Other children...", "Your friend does...")
   - Threats or fear ("If you don't...", "Something bad will happen...")
   - Bribes or rewards ("If you do this, you'll get...")"""""
    
    # Language-specific conversation phrases
    conversation_phrases = {
        "tr": ('"Ne düşünüyorsun?"', '"Biliyor musun?"'),
        "en": ('"What do you think?"', '"You know what?"'),
        "de": ('"Was denkst du?"', '"Weißt du was?"'),
        "es": ('"¿Qué piensas?"', '"¿Sabes qué?"'),
        "fr": ('"Qu\'en penses-tu?"', '"Tu sais quoi?"'),
        "pt": ('"O que você acha?"', '"Sabe o quê?"'),
        "ar": ('"ما رأيك؟"', '"أتعلم ماذا؟"')
    }
    conv_question, conv_transition = conversation_phrases.get(lang_key, conversation_phrases["en"])
    
    phone_conversation_instruction = f"""
8. CRITICAL - PHONE CONVERSATION FORMAT: This story will be told over the phone in a video call format. The story must:
   - Be written as a CONVERSATION between the character and the child - use direct address and dialogue
   - Use natural, spoken language that sounds like a friendly phone conversation
   - Include questions and responses that feel like a real conversation (e.g., {conv_question})
   - Use conversational transitions like {conv_transition}
   - Make the child feel like they are actively participating in a conversation, not just listening to a monologue
   - Use pauses and natural speech patterns that work well for phone conversations
   - The character should speak directly to the child, as if they are having a real-time conversation"""
    
    # CRITICAL: Check if custom_description contains behavior targeting keywords
    # This determines if we need to add "persuasion constraint" to the prompt
    behavior_keywords = {
        "tr": ["ikna", "durdur", "bırak", "yapma", "yapmama", "etme", "etmeme", "vazgeç", "değiştir"],
        "en": ["persuade", "stop", "convince", "change", "avoid", "prevent", "quit", "give up"],
        "de": ["überzeugen", "aufhören", "stoppen", "ändern", "vermeiden", "verhindern"],
        "es": ["convencer", "detener", "parar", "cambiar", "evitar", "prevenir"],
        "fr": ["convaincre", "arrêter", "cesser", "changer", "éviter", "empêcher"],
        "pt": ["convencer", "parar", "parar de", "mudar", "evitar", "prevenir", "desistir"],
        "ar": ["إقناع", "توقف", "تغيير", "تجنب", "منع", "الاستسلام"]
    }
    
    lang_key_for_keywords = language[:2] if len(language) >= 2 else "en"
    keywords = behavior_keywords.get(lang_key_for_keywords, behavior_keywords["en"])
    
    has_behavior_target = False
    target_behavior = None
    if custom_description:
        desc_lower = custom_description.lower()
        # Check if description contains behavior targeting keywords
        for keyword in keywords:
            if keyword in desc_lower:
                has_behavior_target = True
                # Extract the behavior from description (e.g., "tükürmemeye ikna etmek" → "tükürmek")
                # Try to find the behavior verb/noun before the keyword
                target_behavior = custom_description
                break
    
    # Build behavior targeting instruction if custom_description contains behavior target
    behavior_instruction = ""
    if has_behavior_target and target_behavior:
        behavior_instruction = f"""
CRITICAL - BEHAVIOR TARGETING (MOST IMPORTANT):
The parent's specific request: "{target_behavior}"

IMPORTANT RULE:
The story MUST directly address the target behavior mentioned in the parent's request.
The main message MUST be about persuading the child to stop or change the specific behavior.
Do NOT generate a general emotional story or generic topic story.
Mention the behavior explicitly in a child-friendly way.

REQUIREMENTS:
1. The story MUST focus on the specific behavior: {target_behavior}
2. The character MUST gently persuade the child to stop or change this behavior
3. Use positive, child-friendly language to address the behavior (e.g., "tükürmek" → "tükürmemek", "spitting" → "not spitting")
4. The story should show why the behavior is not helpful and what positive alternatives exist
5. Do NOT create a generic story about emotions or general topics - the story MUST be specifically about changing this behavior
6. The behavior should be mentioned naturally throughout the story in a child-friendly way

EXAMPLE:
- If parent says "tükürmemeye ikna etmek istiyorum" → Story MUST be about NOT spitting, showing why spitting is not good, and encouraging the child to stop spitting
- If parent says "persuade child to stop hitting" → Story MUST be about NOT hitting, showing why hitting hurts others, and encouraging gentle touch
- Do NOT create a general "emotional regulation" story - create a story SPECIFICALLY about the target behavior

"""
    
    # Build structure templates (language-agnostic)
    quick_structure = f"""
QUICK STORIES ({target_duration_min}-{target_duration_max} min, {target_word_count} words) - Follow this exact 5-part structure:

1. EMPATHY OPENING (~10%): 1-2 sentences validating child's feelings/situation
2. MINI STORY (~30%): Brief story about animal/character facing same problem
3. 3-STEP ROUTINE (~40%): Present exactly 3 actionable, concrete steps as clear commands. Character demonstrates these steps.
4. SUCCESS (~15%): Character tries routine, experiences positive concrete result
5. CLOSING (~5%): End with exactly 2 open-ended questions inviting child to try the routine

Requirements: Minimum {target_word_count} words. Each section flows naturally. Steps must be practical and age-appropriate for 2-8 year olds.
"""
    
    dreamy_structure = f"""
DREAMY STORIES ({target_duration_min}-{target_duration_max} min, {target_word_count} words) - Flexible structure:

1. OPENING (~15%): Warm greeting + introduce topic
2. DEVELOPMENT (~60%): Main message with explanation, examples, actionable tip
3. CONCLUSION (~25%): Wrap up + warm farewell

Requirements: Clear beginning/middle/end. Stay focused on ONE topic. Use concrete examples and positive reinforcement.
"""
    
    prompt = f"""You are {character_name}, a friendly character having a phone conversation with a child{child_part} and telling them a story.

CRITICAL - CHARACTER IDENTITY & PERSONA:
{persona}

IMPORTANT - STORY VOICE & STYLE:
The story MUST be written from {character_name}'s perspective, using their unique personality, speech style, and characteristics. 
- Speak exactly as {character_name} would speak, using their natural voice and personality traits
- Use {character_name}'s characteristic expressions, tone, and way of thinking
- The story should feel like it's genuinely coming from {character_name}'s own experiences and worldview
- Every word, every sentence should reflect {character_name}'s unique persona and character
- Do NOT write a generic story - write it as if {character_name} themselves is telling it from their heart

The parent wants a story about: {topic_for_prompt}
{behavior_instruction}
IMPORTANT INSTRUCTIONS:
1. CRITICAL: If the topic description contains spelling or grammar errors, you MUST correct them automatically:
   - "gitmemek" → "giymemek" (to wear)
   - "mont gitmemek" → "mont giymemek" (to wear a coat)
   - "kışın mont gitmemek" → "kışın mont giymemek" (to wear a winter coat)
   - "sakınlesmemek" → "sakinleşmemek" (to calm down)
   - Always use the CORRECT version in your story, never repeat the error.
2. Write the story in {language}. Use correct grammar and spelling for {language}.
3. The story must be 100% child-friendly: no violence, scary content, inappropriate language, or negative themes.
4. Keep the story positive, educational, and age-appropriate for children aged 2-8.
5. Understand the CORRECTED topic meaning and create a story that addresses the actual intent (e.g., if corrected to "mont giymemek", create a story about wearing a coat, not about going somewhere).{child_name_instruction}{pedagogical_instruction}{phone_conversation_instruction}

Create a calming, age-appropriate story for a phone conversation that takes approximately {target_duration_min}-{target_duration_max} minutes when spoken aloud. The story should be:
- Written as a natural phone conversation between you and the child
- Positive and reassuring
- Suitable for children aged 2-8
- Calming and gentle
- Engaging but not overstimulating

CRITICAL PEDAGOGICAL STRUCTURE (MANDATORY):
{quick_structure if story_length == "quick" else dreamy_structure}

DURATION & WORD COUNT (CRITICAL):
- Target: {target_word_count} words (±10%: {int(target_word_count * 0.9)}-{int(target_word_count * 1.1)} words)
- Duration: {target_duration_min}-{target_duration_max} minutes when spoken (120 words/minute)
- Word count directly controls duration - stay within range

- Use correct {language} grammar and spelling throughout
- Use conversational, spoken language that sounds natural in a phone call
{f" - CRITICAL: Use the child's name ({child_name}) multiple times throughout the story when addressing the child. Address the child directly by name, for example: {child_name_example}. The child's name should appear at least 3-5 times naturally in the story." if child_name else ""}

CRITICAL: Filter out any inappropriate words or themes. The story must be completely safe for children. Write it as if you are having a warm, friendly phone conversation with the child.

FORMAT:
- Start directly with conversation (no title/heading)
- Character speaks naturally as if answering a phone call

COMPLETION (MANDATORY):
- Story MUST be complete: {target_word_count} words (±10%), all sentences finished
- End with warm, positive closing (natural phone call conclusion)
- If running out of tokens: complete current sentence + add closing

Story:"""
    
    # CONTROL 2: Add debug request payload to prompt for verification
    if debug_request_payload:
        import json
        debug_section = f"""

DEBUG REQUEST PAYLOAD (for verification only - do not change these values):
{json.dumps(debug_request_payload, indent=2, ensure_ascii=False)}

CRITICAL: The story MUST use the character and topic from the debug_request_payload above.
- Character: {debug_request_payload.get('character_slug_normalized', character)}
- Topic: {debug_request_payload.get('topic_mapped', topic)}
- Child Name: {debug_request_payload.get('child_name', child_name or 'N/A')}
"""
        prompt += debug_section
    
    print(f"📝 [generate_story_text] Generating story:")
    print(f"   Character: {character} (display: {character_name})")
    print(f"   Topic: {topic}")
    print(f"   Target duration: {target_duration_min}-{target_duration_max} minutes")
    print(f"   Target words: {target_word_count}")
    print(f"   Max tokens: {max_tokens}")
    
    # Enhanced safety instructions for strict mode
    if strict_safety:
        safety_rules = """
CRITICAL SAFETY RULES (MANDATORY - STRICT MODE):
1. All content must be 100% child-friendly and age-appropriate (ages 2-8).
2. ABSOLUTELY NO: violence, scary content, inappropriate language, negative themes, profanity, adult content, or any harmful material.
3. If the parent's topic contains ANY inappropriate words or themes, IGNORE them completely and create a positive, safe story instead.
4. Focus ONLY on: friendship, kindness, learning, growth, positive emotions, and age-appropriate challenges.
5. Stories must be calming, reassuring, and educational.
6. Use only positive, uplifting language throughout.
7. If unsure about any content, err on the side of caution and make it more positive and safe.
8. Automatically correct any spelling or grammar errors in the parent's topic description.
9. Use correct grammar and spelling for the target language ({language}).
"""
    else:
        safety_rules = """
CRITICAL RULES:
1. All content must be 100% child-friendly and age-appropriate (ages 2-8).
2. NO violence, scary content, inappropriate language, or negative themes.
3. Automatically correct any spelling or grammar errors in the parent's topic description.
4. Use correct grammar and spelling for the target language ({language}).
5. Keep stories positive, educational, and calming.
6. If you detect any inappropriate words or themes in the topic, replace them with safe, positive alternatives.
"""
    
    system_message = f"""You are {character_name}, a kind and gentle character who tells calming stories to children.

{safety_rules}

Your stories must always be safe, positive, and suitable for young children."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_tokens,
        temperature=0.8
    )
    
    generated_text = response.choices[0].message.content.strip()
    word_count = len(generated_text.split())
    
    # CRITICAL: Check if story is incomplete (cut off mid-sentence)
    # Common indicators: ends with incomplete words, no closing, abrupt ending
    min_words = int(target_word_count * 0.9)
    max_words = int(target_word_count * 1.1)
    
    incomplete_indicators = [
        generated_text.endswith("und"),  # German "and" cut off
        generated_text.endswith("and"),  # English "and" cut off
        generated_text.endswith("et"),  # French "and" cut off
        generated_text.endswith("y"),  # Spanish "and" cut off
        generated_text.endswith("ve"),  # Turkish "and" cut off
        not generated_text.rstrip().endswith((".", "!", "?")),  # No punctuation at end
        word_count < int(target_word_count * 0.8),  # Significantly under word count
    ]
    
    is_incomplete = any(incomplete_indicators) or (
        word_count < int(target_word_count * 0.8) and 
        not generated_text.rstrip().endswith((".", "!", "?"))
    )
    
    # If incomplete, try to regenerate with increased max_tokens
    # COST OPTIMIZATION: Only retry if story is incomplete (minimizes unnecessary token usage)
    if is_incomplete:
        print(f"⚠️ [generate_story_text] Story appears incomplete (word_count: {word_count}, ends with: '{generated_text[-50:]}')")
        
        # Use retry_max_tokens parameter if provided, otherwise calculate 1.5x
        # This allows per-length-type retry limits (e.g., quick: 600, dreamy: 1500)
        if retry_max_tokens is None:
            retry_max_tokens = int(max_tokens * 1.5)
        
        print(f"   Retrying with increased max_tokens: {max_tokens} → {retry_max_tokens}")
        
        # Retry with increased token limit
        retry_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            max_tokens=retry_max_tokens,
            temperature=0.8
        )
        generated_text = retry_response.choices[0].message.content.strip()
        word_count = len(generated_text.split())
        print(f"   ✅ Retry completed: word_count={word_count}")
    
    # Calculate estimated duration (assuming ~120 words per minute for spoken text)
    estimated_duration_minutes = word_count / 120.0
    
    print(f"✅ [generate_story_text] Story generated:")
    print(f"   Word count: {word_count} (target: {target_word_count}, range: {min_words}-{max_words})")
    print(f"   Estimated duration: {estimated_duration_minutes:.1f} minutes (target: {target_duration_min}-{target_duration_max} minutes)")
    print(f"   Last 100 chars: '{generated_text[-100:]}'")
    
    # Warn if word count or duration is outside acceptable range
    if word_count < min_words:
        print(f"⚠️ [generate_story_text] WARNING: Story is too short ({word_count} words < {min_words} words)")
        print(f"   Estimated duration ({estimated_duration_minutes:.1f} min) is below target ({target_duration_min} min)")
    elif word_count > max_words:
        print(f"⚠️ [generate_story_text] WARNING: Story is too long ({word_count} words > {max_words} words)")
        print(f"   Estimated duration ({estimated_duration_minutes:.1f} min) exceeds target ({target_duration_max} min)")
    elif estimated_duration_minutes < target_duration_min:
        print(f"⚠️ [generate_story_text] WARNING: Estimated duration ({estimated_duration_minutes:.1f} min) is below target ({target_duration_min} min)")
    elif estimated_duration_minutes > target_duration_max:
        print(f"⚠️ [generate_story_text] WARNING: Estimated duration ({estimated_duration_minutes:.1f} min) exceeds target ({target_duration_max} min)")
    else:
        print(f"✅ [generate_story_text] Story duration and word count are within acceptable range")
    
    return generated_text


async def generate_story_audio(text: str, character_id: str, language: str) -> str:
    """Generate audio using TTS and upload to Firebase Storage."""
    # Use existing TTS generation
    style = {"stability": 0.7, "similarity_boost": 0.85, "style": 0.6}
    audio_url = await generate_tts(
        text=text,
        style=style,
        lang=language,
        character=character_id
    )
    return audio_url


async def get_audio_duration(audio_url: str) -> int:
    """Get audio duration in seconds.
    
    PREFERRED: Read from local file (faster, no SSL issues)
    FALLBACK: Download from URL if local file not found
    """
    try:
        # PREFERRED: Try to extract local file path from audio_url
        # Format: https://64.226.88.203/local-audio/{character}_{topic}_{storyId}_{sceneIndex}?lang={lang}
        # Local path: AUDIO_BASE_DIR / character / lang / {topic}_{storyId}_{sceneIndex}.wav
        from urllib.parse import urlparse, parse_qs
        
        parsed_url = urlparse(audio_url)
        audio_id = parsed_url.path.split('/')[-1]  # e.g., "sunny_bedtime_storyId_0.wav"
        lang = parse_qs(parsed_url.query).get('lang', ['en'])[0]
        
        # Remove extension
        audio_id_clean = audio_id.replace('.wav', '').replace('.mp3', '')
        parts = audio_id_clean.split('_')
        
        if len(parts) >= 3:
            character = parts[0].lower()
            # Try to find local file (check both .wav and .mp3)
            for ext in ['.wav', '.mp3']:
                # Try with story ID (custom story format)
                if len(parts) >= 4:
                    # Format: character_topic_storyId_sceneIndex
                    topic_and_story = '_'.join(parts[1:-1])  # Everything except first (character) and last (sceneIndex)
                    scene_index = parts[-1]
                    local_path = AUDIO_BASE_DIR / character / lang / f"{topic_and_story}_{scene_index}{ext}"
                else:
                    # Format: character_topic_sceneIndex (system story)
                    topic = '_'.join(parts[1:-1])
                    scene_index = parts[-1]
                    local_path = AUDIO_BASE_DIR / character / lang / f"{topic}_{scene_index}{ext}"
                
                if local_path.exists() and local_path.stat().st_size > 0:
                    print(f"✅ [get_audio_duration] Using local file: {local_path}")
                    probe = ffmpeg.probe(str(local_path))
                    duration = float(probe["format"]["duration"])
                    return int(duration)
        
        # FALLBACK: Download from URL if local file not found
        print(f"⚠️ [get_audio_duration] Local file not found, downloading from URL: {audio_url}")
        import httpx
        # Disable SSL verification for self-signed certificates (temporary workaround)
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(audio_url, timeout=30.0)
            audio_data = response.content
        
        # Use ffmpeg to get duration
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        
        probe = ffmpeg.probe(tmp_path)
        duration = float(probe["format"]["duration"])
        
        os.unlink(tmp_path)
        return int(duration)
    except Exception as e:
        print(f"⚠️ Error getting audio duration: {e}")
        import traceback
        traceback.print_exc()
        return 180  # Default 3 minutes


def correct_common_errors(text: str) -> str:
    """Correct common spelling and grammar errors in Turkish text."""
    # Common error corrections (Turkish)
    corrections = {
        # "gitmemek" → "giymemek" (common typo)
        "mont gitmemek": "mont giymemek",
        "kışın mont gitmemek": "kışın mont giymemek",
        " mont gitmemek": " mont giymemek",
        " kışın mont gitmemek": " kışın mont giymemek",
        # "sakınlesmemek" → "sakinleşmemek" (common typo)
        "sakınlesmemek": "sakinleşmemek",
        "sakınlesmek": "sakinleşmek",
        "sakınlesmesi": "sakinleşmesi",
        # "gitmek" → "giymek" (when context suggests clothing)
        "mont gitmek": "mont giymek",
        "kışın mont gitmek": "kışın mont giymek",
        " mont gitmek": " mont giymek",
        " kışın mont gitmek": " kışın mont giymek",
    }
    
    corrected = text
    for error, correction in corrections.items():
        if error in corrected.lower():
            # Preserve original case
            if error.lower() in corrected.lower():
                corrected = corrected.replace(error, correction)
                corrected = corrected.replace(error.capitalize(), correction.capitalize())
                corrected = corrected.replace(error.upper(), correction.upper())
    
    return corrected


async def map_topic_with_ai(topic_description: str, language: str) -> Optional[str]:
    """Use AI to intelligently map a free-form topic description to a canonical topic slug.
    
    This is more flexible than keyword-based mapping and handles:
    - Free-form descriptions
    - Context-aware understanding
    - Spelling/grammar errors (already corrected)
    - Multi-language support
    
    Args:
        topic_description: Free-form topic description (e.g., "kışın mont giymemek", "bedtime — Parent context: Yatmadan önce sakinleşmemek")
        language: Language code (e.g., "tr", "en")
        
    Returns:
        Canonical topic slug (e.g., "transitions", "bedtime", "nutrition") or None if mapping fails
    """
    if not settings.OPENAI_API_KEY:
        return None
    
    # List of canonical topics (from topic_mapping.py)
    canonical_topics = [
        "bedtime", "nutrition", "friendship", "confidence", "emotional_regulation",
        "transitions", "kindness", "screen_time", "sharing", "sibling", "imagination"
    ]
    
    # Language-specific topic descriptions for better AI understanding
    topic_descriptions = {
        "tr": {
            "bedtime": "uyku, yatma, uyku vakti, rahatlama",
            "nutrition": "yemek, beslenme, yemek yemek, iştah",
            "friendship": "arkadaşlık, paylaşma, sosyal ilişkiler",
            "confidence": "özgüven, cesaret, kendine güven",
            "emotional_regulation": "duygusal düzenleme, öfke, kaygı, sakinleşme",
            "transitions": "geçişler, rutin değişiklikleri, giyinme, hazırlanma",
            "kindness": "naziklik, iyilik, kardeşlere karşı nazik olma",
            "screen_time": "ekran süresi, teknoloji kullanımı",
            "sharing": "paylaşma, oyuncak paylaşma",
            "sibling": "kardeş ilişkileri, kardeşler arası anlaşma",
            "imagination": "hayal gücü, yaratıcılık, oyun"
        },
        "en": {
            "bedtime": "sleep, going to bed, sleep time, relaxation",
            "nutrition": "eating, food, nutrition, appetite",
            "friendship": "friendship, sharing, social relationships",
            "confidence": "self-confidence, courage, self-esteem",
            "emotional_regulation": "emotional regulation, anger, anxiety, calming down",
            "transitions": "transitions, routine changes, getting dressed, preparing",
            "kindness": "kindness, being kind to siblings",
            "screen_time": "screen time, technology use",
            "sharing": "sharing, sharing toys",
            "sibling": "sibling relationships, getting along with siblings",
            "imagination": "imagination, creativity, play"
        }
    }
    
    lang_key = language[:2] if len(language) >= 2 else "en"
    topic_descriptions_lang = topic_descriptions.get(lang_key, topic_descriptions["en"])
    
    # Build topic list for AI
    topics_list = "\n".join([
        f"- {topic}: {topic_descriptions_lang.get(topic, topic)}"
        for topic in canonical_topics
    ])
    
    try:
        import openai
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        
        prompt = f"""You are a topic classification assistant. Your task is to map a parent's topic description to the most appropriate canonical topic.

Canonical topics:
{topics_list}

Examples:
- "kışın mont giymemek" → "transitions" (getting dressed, wearing clothes)
- "yemek yemek istemiyor" → "nutrition" (eating, food)
- "uykuya dalmakta zorlanıyor" → "bedtime" (sleep, going to bed)
- "kardeşiyle paylaşmak istemiyor" → "sharing" (sharing toys)
- "okula gitmek istemiyor" → "transitions" (routine changes, school start)

Parent's topic description: "{topic_description}"

Instructions:
1. Understand the parent's intent from the description
2. If the description contains spelling/grammar errors, correct them mentally (e.g., "gitmemek" → "giymemek", "mont gitmemek" → "mont giymemek")
3. Map to the MOST APPROPRIATE canonical topic from the list above
4. Consider the context: "mont giymemek" is about getting dressed (transitions), not about going somewhere
5. Return ONLY the canonical topic slug (e.g., "transitions", "bedtime", "nutrition")
6. Do NOT return explanations, just the topic slug

Canonical topic:"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use mini for fast, cheap topic mapping
            messages=[
                {"role": "system", "content": "You are a topic classification assistant. Return only the canonical topic slug, no explanations. You must choose from the provided canonical topics list."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,  # Very low temperature for consistent, deterministic mapping
            max_tokens=20  # Just need the topic slug
        )
        
        ai_topic = response.choices[0].message.content.strip().lower()
        
        # Clean up AI response (remove quotes, extra whitespace, etc.)
        ai_topic = ai_topic.strip('"').strip("'").strip()
        
        # Validate that AI returned a valid canonical topic
        if ai_topic in canonical_topics:
            print(f"✅ [map_topic_with_ai] AI successfully mapped: '{topic_description}' → '{ai_topic}'")
            return ai_topic
        else:
            print(f"⚠️ [map_topic_with_ai] AI returned invalid topic: '{ai_topic}' (not in canonical list), falling back to keyword-based mapping")
            print(f"   Available topics: {canonical_topics}")
            return None
            
    except Exception as e:
        print(f"⚠️ [map_topic_with_ai] Error mapping topic with AI: {e}")
        return None


async def moderate_content(content: str, language: str = "en") -> dict:
    """Multi-layer content moderation using AI and rule-based filtering.
    
    This function provides:
    1. Context-aware pre-processing (negative behavior detection)
    2. AI-based moderation (OpenAI Moderation API)
    3. Rule-based filtering (profanity, inappropriate themes)
    4. Pedagogical safety checks (child-appropriate content)
    5. Fraud detection (spam patterns, abuse)
    
    Args:
        content: Text content to moderate (topic, description, or story text)
        language: Language code for language-specific checks
        
    Returns:
        dict with keys:
        - is_safe: bool - Whether content is safe
        - reason: str - Reason if unsafe
        - severity: str - "low", "medium", "high", "critical"
        - sanitized: str - Sanitized version if applicable
        - flags: list - List of detected issues
    """
    result = {
        "is_safe": True,
        "reason": None,
        "severity": "low",
        "sanitized": content,
        "flags": []
    }
    
    if not content or len(content.strip()) == 0:
        return result
    
    content_lower = content.lower()
    
    # CRITICAL: Pre-process negative behavior phrases before moderation
    # This prevents false positives where "vurmamaya" (not hitting) is flagged as violence
    # Negative behavior phrases indicate POSITIVE parenting goals (stopping bad behavior)
    negative_behavior_patterns = {
        "tr": [
            r"vurmamaya", r"vurmama", r"tukurmemeye", r"tukurme", r"yapmamaya", r"yapmama",
            r"etmemeye", r"etmeme", r"durdurmaya", r"durdurma", r"bırakmaya", r"bırakma",
            r"vazgeçmeye", r"vazgeçme", r"değiştirmeye", r"değiştirme", r"ikna etmek",
            r"teşvik etmek", r"engellemek", r"önlemek"
        ],
        "en": [
            r"not hitting", r"not hitting", r"not spitting", r"stop hitting", r"stop spitting",
            r"don't hit", r"don't spit", r"persuade.*stop", r"convince.*not", r"prevent.*from",
            r"avoid.*doing", r"quit.*doing", r"give up.*doing"
        ],
        "de": [
            r"nicht schlagen", r"nicht spucken", r"aufhören.*zu", r"verhindern.*dass"
        ],
        "es": [
            r"no golpear", r"no escupir", r"dejar de", r"evitar.*hacer"
        ],
        "fr": [
            r"ne pas frapper", r"ne pas cracher", r"arrêter de", r"éviter de"
        ]
    }
    
    lang_key = language[:2] if len(language) >= 2 else "en"
    negative_patterns = negative_behavior_patterns.get(lang_key, negative_behavior_patterns["en"])
    
    # Check if content contains negative behavior phrases (indicating positive parenting goals)
    has_negative_behavior_context = False
    for pattern in negative_patterns:
        if re.search(pattern, content_lower, re.IGNORECASE):
            has_negative_behavior_context = True
            print(f"✅ [moderate_content] Detected negative behavior context (positive parenting goal): '{pattern}' in content")
            break
    
    # If negative behavior context is detected, create a context-aware version for moderation
    # This helps OpenAI Moderation API understand the positive intent
    moderation_input = content
    if has_negative_behavior_context:
        # Add context to help moderation API understand this is about positive behavior change
        context_prefix = {
            "tr": "Ebeveyn çocuğunu olumlu davranışa teşvik etmek istiyor: ",
            "en": "Parent wants to encourage positive behavior in child: ",
            "de": "Elternteil möchte positives Verhalten beim Kind fördern: ",
            "es": "Padre quiere fomentar comportamiento positivo en el niño: ",
            "fr": "Parent veut encourager un comportement positif chez l'enfant: "
        }
        moderation_input = context_prefix.get(lang_key, context_prefix["en"]) + content
        print(f"🔄 [moderate_content] Added context for moderation API to understand positive intent")
    
    # Layer 1: Rule-based filtering (fast, deterministic)
    # Profanity and inappropriate words (multi-language)
    profanity_patterns = {
        "tr": ["küfür", "lanet", "pislik", "aptal", "salak", "gerizekalı"],
        "en": ["fuck", "shit", "damn", "bitch", "asshole", "stupid", "idiot"],
        "de": ["scheiße", "verdammt", "idiot", "dumm"],
        "es": ["joder", "mierda", "idiota", "estúpido"],
        "fr": ["merde", "putain", "con", "idiot", "stupide"]
    }
    
    # Violence and inappropriate themes
    inappropriate_themes = [
        "violence", "kill", "death", "murder", "weapon", "gun", "knife",
        "adult", "explicit", "sexual", "porn", "drug", "alcohol",
        "terror", "bomb", "attack", "hate", "racist"
    ]
    
    lang_key = language[:2] if len(language) >= 2 else "en"
    profanity_list = profanity_patterns.get(lang_key, profanity_patterns["en"])
    
    # Check for profanity (word boundary matching to avoid false positives)
    for word in profanity_list:
        # Use word boundary regex to match whole words only (prevents false positives like "hungry" matching "gun")
        pattern = r'\b' + re.escape(word) + r'\b'
        if re.search(pattern, content_lower):
            result["is_safe"] = False
            result["reason"] = f"Inappropriate language detected: {word}"
            # Profanity severity: medium (can be auto-corrected to safe alternative)
            result["severity"] = "medium"
            result["flags"].append("profanity")
            return result
    
    # Check for inappropriate themes (word boundary matching to avoid false positives)
    for theme in inappropriate_themes:
        # Use word boundary regex to match whole words only
        # This prevents false positives like "hungry" matching "gun", "jungle" matching "gun", etc.
        pattern = r'\b' + re.escape(theme) + r'\b'
        if re.search(pattern, content_lower):
            result["is_safe"] = False
            result["reason"] = f"Inappropriate theme detected: {theme}"
            # Theme severity: critical for violence/adult content, high for others
            # Critical themes cannot be auto-corrected (security risk)
            if theme in ["violence", "kill", "murder", "weapon", "gun", "knife", "terror", "bomb", "attack", "hate", "racist"]:
                result["severity"] = "critical"  # Cannot auto-correct, must reject
            elif theme in ["adult", "explicit", "sexual", "porn", "drug", "alcohol"]:
                result["severity"] = "critical"  # Cannot auto-correct, must reject
            else:
                result["severity"] = "high"  # May be auto-corrected in some cases
            result["flags"].append("inappropriate_theme")
            return result
    
    # Layer 2: AI-based moderation (OpenAI Moderation API)
    if settings.OPENAI_API_KEY:
        try:
            import openai
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            
            # Use context-aware input if negative behavior context was detected
            moderation_response = client.moderations.create(input=moderation_input)
            moderation_result = moderation_response.results[0]
            
            # Check moderation flags
            if moderation_result.flagged:
                categories = moderation_result.categories
                flagged_categories = [cat for cat, flagged in categories.dict().items() if flagged]
                
                # CRITICAL: If negative behavior context is detected and only "violence" is flagged,
                # this is likely a false positive (e.g., "vurmamaya" = not hitting = positive goal)
                if has_negative_behavior_context and "violence" in flagged_categories and len(flagged_categories) == 1:
                    # Check violence score - if it's low/medium, it's likely a false positive
                    violence_score = moderation_result.category_scores.violence
                    if violence_score < 0.5:  # Low confidence in violence detection
                        print(f"✅ [moderate_content] False positive detected: 'violence' flag with negative behavior context")
                        print(f"   Violence score: {violence_score:.3f} (low confidence)")
                        print(f"   Content is about positive behavior change, not actual violence")
                        # Allow content - it's about positive parenting goals
                        result["is_safe"] = True
                        result["flags"].append("violence_false_positive_ignored")
                        return result
                    elif violence_score < 0.7:  # Medium confidence - review but allow
                        print(f"⚠️ [moderate_content] Medium confidence violence flag with negative behavior context")
                        print(f"   Violence score: {violence_score:.3f} (medium confidence)")
                        print(f"   Allowing content but flagging for review")
                        result["is_safe"] = True
                        result["severity"] = "low"
                        result["flags"].append("violence_review_needed")
                        return result
                
                # High confidence violence flag or multiple flags → reject
                result["is_safe"] = False
                result["reason"] = f"Content flagged by moderation API: {', '.join(flagged_categories)}"
                result["severity"] = "critical"
                result["flags"].extend(flagged_categories)
                
                # Log for security monitoring
                print(f"🚨 [moderate_content] Content flagged: {content[:100]}...")
                print(f"   Categories: {flagged_categories}")
                print(f"   Scores: {moderation_result.category_scores}")
                
                return result
        except Exception as e:
            print(f"⚠️ [moderate_content] Error calling moderation API: {e}")
            # Continue with rule-based checks if API fails
    
    # Layer 3: Pedagogical safety checks
    # Check for content that might be psychologically harmful to children
    harmful_patterns = [
        "fear", "scary", "monster", "ghost", "death", "dying",
        "abandon", "reject", "hate", "worthless", "useless"
    ]
    
    # Context-aware: these words might be okay in certain contexts
    # But we flag them for review
    for pattern in harmful_patterns:
        if pattern in content_lower:
            result["flags"].append(f"potentially_harmful_{pattern}")
            # Don't block, but flag for review
    
    # Layer 4: Fraud detection patterns
    spam_patterns = [
        "http://", "https://", "www.", ".com", ".net", ".org",
        "click here", "buy now", "free money", "lottery", "winner"
    ]
    
    for pattern in spam_patterns:
        if pattern in content_lower:
            result["is_safe"] = False
            result["reason"] = f"Spam pattern detected: {pattern}"
            result["severity"] = "medium"
            result["flags"].append("spam")
            return result
    
    return result


async def get_safe_alternative_topic(inappropriate_topic: str, language: str, flags: list) -> str:
    """Get a safe alternative topic based on the inappropriate content detected.
    
    This provides automatic correction by mapping inappropriate topics to safe alternatives.
    
    Args:
        inappropriate_topic: The original topic that was flagged
        language: Language code
        flags: List of moderation flags (e.g., ["profanity", "inappropriate_theme"])
        
    Returns:
        Safe alternative topic slug (e.g., "bedtime", "friendship", "kindness")
    """
    # Map inappropriate content to safe alternatives based on flags
    # This provides automatic correction instead of rejection
    
    # If profanity detected → map to a positive topic
    if "profanity" in flags:
        return "kindness"  # Focus on positive behavior
    
    # If inappropriate theme detected → map to educational topic
    if "inappropriate_theme" in flags:
        if any("violence" in flag or "hate" in flag for flag in flags):
            return "friendship"  # Focus on positive relationships
        elif any("adult" in flag or "sexual" in flag for flag in flags):
            return "bedtime"  # Safe, calming topic
        else:
            return "kindness"  # General positive topic
    
    # If spam detected → use default safe topic
    if "spam" in flags:
        return "bedtime"  # Default safe topic
    
    # Default fallback: use a positive, educational topic
    return "friendship"


async def sanitize_and_validate_input(topic: str, custom_description: Optional[str], language: str, auto_correct: bool = True) -> tuple[str, Optional[str], bool, Optional[dict], Optional[str]]:
    """Sanitize and validate user input before story generation.
    
    BEST PRACTICE: Auto-correction mode
    - If inappropriate content is detected with LOW/MEDIUM severity → automatically correct to safe alternative
    - If inappropriate content is detected with HIGH/CRITICAL severity → reject (security)
    
    Args:
        topic: Original topic from user
        custom_description: Optional custom description
        language: Language code
        auto_correct: If True, automatically correct low/medium severity issues instead of rejecting
        
    Returns:
        tuple: (sanitized_topic, sanitized_description, is_valid, moderation_result, auto_corrected_topic)
        - sanitized_topic: Cleaned topic (may be auto-corrected)
        - sanitized_description: Cleaned description (may be None if rejected)
        - is_valid: Whether content is valid (True if safe or auto-corrected, False if rejected)
        - moderation_result: dict with moderation details if validation failed, None if passed
        - auto_corrected_topic: Safe alternative topic if auto-correction was applied, None otherwise
    """
    auto_corrected_topic = None
    
    # Moderate topic
    topic_moderation = await moderate_content(topic, language)
    if not topic_moderation["is_safe"]:
        severity = topic_moderation.get("severity", "medium")
        flags = topic_moderation.get("flags", [])
        
        # Auto-correction: For low/medium severity, automatically correct to safe alternative
        if auto_correct and severity in ["low", "medium"]:
            safe_alternative = await get_safe_alternative_topic(topic, language, flags)
            print(f"🔄 [sanitize_and_validate_input] Auto-correcting topic: '{topic}' → '{safe_alternative}' (severity: {severity})")
            print(f"   Reason: {topic_moderation['reason']}")
            auto_corrected_topic = safe_alternative
            # Use safe alternative as sanitized topic
            sanitized_topic = safe_alternative
        else:
            # High/critical severity → reject for security
            print(f"🚨 [sanitize_and_validate_input] Topic rejected (severity: {severity}): {topic_moderation['reason']}")
            return None, None, False, topic_moderation, None
    
    # Moderate custom description if provided
    sanitized_description = None
    desc_moderation = None
    if custom_description:
        desc_moderation = await moderate_content(custom_description, language)
        if not desc_moderation["is_safe"]:
            severity = desc_moderation.get("severity", "medium")
            flags = desc_moderation.get("flags", [])
            
            # Auto-correction: For low/medium severity, remove inappropriate parts
            if auto_correct and severity in ["low", "medium"]:
                # Remove inappropriate words but keep safe parts
                sanitized_description = desc_moderation.get("sanitized", "")
                # If sanitized is empty or still unsafe, use empty description
                if not sanitized_description or len(sanitized_description.strip()) < 3:
                    sanitized_description = None
                    print(f"🔄 [sanitize_and_validate_input] Auto-correcting description: removed inappropriate content")
                else:
                    print(f"🔄 [sanitize_and_validate_input] Auto-correcting description: '{custom_description}' → '{sanitized_description}' (severity: {severity})")
            else:
                # High/critical severity → reject description
                print(f"🚨 [sanitize_and_validate_input] Description rejected (severity: {severity}): {desc_moderation['reason']}")
                return None, None, False, desc_moderation, auto_corrected_topic
        else:
            sanitized_description = desc_moderation["sanitized"]
    
    # Correct common errors (spelling/grammar)
    if not auto_corrected_topic:
        sanitized_topic = correct_common_errors(topic_moderation["sanitized"])
    else:
        # Already auto-corrected, just ensure it's clean
        sanitized_topic = auto_corrected_topic
    
    return sanitized_topic, sanitized_description, True, None, auto_corrected_topic


def sanitize_topic(topic: str) -> str:
    """Sanitize topic to remove harmful content and map to canonical topic.
    
    NOTE: This is a legacy function. Use sanitize_and_validate_input() for new code.
    """
    # First, correct common errors in topic description
    corrected_topic = correct_common_errors(topic)
    
    # Then, map topic to canonical slug (handles free-form descriptions)
    mapped_topic = map_topic(corrected_topic)
    
    # Basic sanitization - in production, use a proper content moderation API
    forbidden_words = ["violence", "adult", "explicit"]
    topic_lower = mapped_topic.lower()
    for word in forbidden_words:
        if word in topic_lower:
            return "bedtime"  # Safe fallback topic
    return mapped_topic


def split_text_into_scenes(text: str, character: str, language: str, child_name: Optional[str] = None) -> List[Dict]:
    """
    Split story text into scenes with videoKeys using analyze_text_for_video_key.
    VideoKey priority: talking > wave > raise_hand (lean_closer minimized)
    """
    from services.story_composer import analyze_text_for_video_key
    import re
    
    # Available videoKeys for character (fallback to talking if not exists)
    # Most characters have: talking, wave, lean_closer, raise_hand
    AVAILABLE_VIDEO_KEYS = {"talking", "wave", "lean_closer", "raise_hand", "hand_on_hip", "side_glance"}
    FALLBACK_VIDEO_KEY = "talking"  # Default fallback
    
    def get_safe_video_key(scene_type: str, text_content: str, lang: str) -> str:
        """Get videoKey with fallback to 'talking' if not available"""
        video_key = analyze_text_for_video_key(scene_type, text_content, lang)
        # If videoKey is lean_closer, prefer talking for most scenes (reduce lean_closer usage)
        if video_key == "lean_closer" and scene_type not in ["question"]:
            return FALLBACK_VIDEO_KEY
        return video_key if video_key in AVAILABLE_VIDEO_KEYS else FALLBACK_VIDEO_KEY
    
    # Split text into paragraphs
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if len(paragraphs) <= 1:
        sentences = re.split(r'[.!?]+\s+', text)
        paragraphs = [s.strip() for s in sentences if s.strip()]
    
    scenes = []
    para_count = len(paragraphs)
    
    # First scene: opening (wave)
    if para_count > 0:
        scene_type = "opening"
        scenes.append({
            "id": "opening_0",
            "type": scene_type,
            "text": paragraphs[0],
            "videoKey": "wave"  # Opening always uses wave
        })
    
    # Middle scenes - prioritize "speak" (talking) over question (lean_closer)
    # Pattern: speak, speak, encouragement (instead of speak, question, encouragement)
    if para_count > 2:
        middle = paragraphs[1:-1]
        # Reduced lean_closer: use speak instead of question for most middle scenes
        scene_types = ["speak", "speak", "encouragement"]  # Changed: question -> speak
        for i, para in enumerate(middle):
            scene_type = scene_types[i] if i < len(scene_types) else "speak"
            scenes.append({
                "id": f"scene_{i+1}",
                "type": scene_type,
                "text": para,
                "videoKey": get_safe_video_key(scene_type, para, language)
            })
    elif para_count == 2:
        scene_type = "speak"
        scenes.append({
            "id": "scene_1",
            "type": scene_type,
            "text": paragraphs[1],
            "videoKey": get_safe_video_key(scene_type, paragraphs[1], language)
        })
    
    # Last scene: closure (wave)
    if para_count > 1:
        scene_type = "closure"
        scenes.append({
            "id": "closure",
            "type": scene_type,
            "text": paragraphs[-1],
            "videoKey": "wave"  # Closure always uses wave
        })
    
    if not scenes:
        scenes.append({
            "id": "scene_0",
            "type": "speak",
            "text": text,
            "videoKey": FALLBACK_VIDEO_KEY
        })
    
    return scenes


async def generate_story_title(story_text: str, language: str, character: str, child_name: Optional[str] = None, topic: Optional[str] = None) -> str:
    """Generate an engaging, child-friendly title for the story using AI.
    
    The title should:
    - Be short and catchy (max 60 characters)
    - Reflect the story's main theme
    - Be appropriate for children
    - Include character name if relevant
    - Be in the correct language
    
    Args:
        story_text: The full story text
        language: Language code (e.g., "tr", "en")
        character: Character slug (e.g., "spiderman", "elsa")
        child_name: Optional child name to personalize the title
        
    Returns:
        Generated title string
    """
    if not settings.OPENAI_API_KEY:
        # Fallback to simple extraction
        return extract_title_from_text(story_text)
    
    try:
        import openai
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Map character slug to display name (language-aware)
        lang_key = language[:2] if len(language) >= 2 else "en"
        
        # Language-specific character display names (shared with generate_story_text)
        # CRITICAL: All characters must be present for consistency between UI and Backend
        # Age-appropriate translations for 2-8 year olds: FUNNY, REALISTIC, SHORT
        # IMPORTANT: Using ASO-safe derivative names (not original copyrighted names)
        character_display_maps = {
            "tr": {
                "spiderman": "Örümcek Savaşçısı",
                "minion": "Sarı Arkadaş",
                "tweety": "Cıvıl Kuş",
                "spongebob": "Baloncuk",
                "elsa": "Buz Prensesi Elisa",
                "tom": "Sinsi Kedi Tim",
                "jerry": "Zeki Fare Herry",
                "ninjaturtles": "Kabuk Kahramanlar",
                "sunny": "Sunny",
                "bubu": "Bubu",
                "luna": "Luna",
                "tiko": "Tiko",
                "mino": "Mino",
                "koko": "Koko",
                "bugsbunny": "Komik Tavşan",
                "ironman": "Metal Kahraman",
                "peppapig": "Domuzcuk",
                "bluey": "Mavi Köpek",
                "pawpatrol": "Kurtarma Köpekleri",
                "moana": "Okyanus Hayalcisi",
                "mario": "Süper Zıplayan",
                "shrek": "Yeşil Dev",
                "pussinboots": "Çizmeli Kedi",
                "sid": "Buz Arkadaşı",
                "dora": "Macera Keşifçisi",
                "olaf": "Kardan Adam Arkadaşı",
                "pikachu": "Sarı Şimşek",
                "scoobydoo": "Gizemli Köpek",
                "winnie": "Winnie",
                "bunny": "Tavşan",
                "barbie": "Pembe Rüya Kızı",
                "tractor": "Traktör",
                "mcqueen": "Yarışçı",
                "hulk": "Yeşil Güçlü Kahraman"
            },
            "en": {
                "spiderman": "Spider Fighter",
                "minion": "Yellow Buddy",
                "tweety": "Chirpy Bird",
                "spongebob": "Bubble",
                "elsa": "Ice Princess Elisa",
                "tom": "Sneaky Tim",
                "jerry": "Clever Herry",
                "ninjaturtles": "Shell Heroes",
                "sunny": "Sunny",
                "bubu": "Bubu",
                "luna": "Luna",
                "tiko": "Tiko",
                "mino": "Mino",
                "koko": "Koko",
                "bugsbunny": "Funny Bunny",
                "ironman": "Metal Hero",
                "peppapig": "Piggy",
                "bluey": "Blue Dog",
                "pawpatrol": "Rescue Dogs",
                "moana": "Ocean Dreamer",
                "mario": "Super Jumper",
                "shrek": "Green Giant",
                "pussinboots": "Boots Cat",
                "sid": "Frost Friend",
                "dora": "Adventure Explorer",
                "olaf": "Snowman Buddy",
                "pikachu": "Yellow Spark",
                "scoobydoo": "Mystery Pup",
                "winnie": "Winnie",
                "bunny": "Bunny",
                "barbie": "Pinko",
                "tractor": "Trac",
                "mcqueen": "Racer",
                "hulk": "Hully"
            },
            "de": {
                "spiderman": "Spinnenkämpfer",
                "minion": "Gelber Freund",
                "tweety": "Zwitschervogel",
                "spongebob": "Blase",
                "elsa": "Eisprinzessin Elisa",
                "tom": "Schlaue Katze Tim",
                "jerry": "Clevere Maus Herry",
                "ninjaturtles": "Schildhelden",
                "sunny": "Sunny",
                "bubu": "Bubu",
                "luna": "Luna",
                "tiko": "Tiko",
                "mino": "Mino",
                "koko": "Koko",
                "bugsbunny": "Lustiger Hase",
                "ironman": "Metall Held",
                "peppapig": "Schweinchen",
                "bluey": "Blauer Hund",
                "pawpatrol": "Rettungshunde",
                "moana": "Ozean Träumer",
                "mario": "Super Springer",
                "shrek": "Grüner Riese",
                "pussinboots": "Stiefel Kater",
                "sid": "Frost Freund",
                "dora": "Abenteuer Entdecker",
                "olaf": "Schneemann Freund",
                "pikachu": "Gelber Funke",
                "scoobydoo": "Geheimnis Welpe",
                "winnie": "Winnie",
                "bunny": "Hase",
                "barbie": "Rosa Traumgirl",
                "tractor": "Traktor",
                "mcqueen": "Rennfahrer",
                "hulk": "Grüner Starker Held"
            },
            "es": {
                "spiderman": "Luchador Araña",
                "minion": "Amigo Amarillo",
                "tweety": "Pájaro Gorjeador",
                "spongebob": "Burbuja",
                "elsa": "Princesa de Hielo Elisa",
                "tom": "Gato Astuto Tim",
                "jerry": "Ratón Inteligente Herry",
                "ninjaturtles": "Héroes Caparazón",
                "sunny": "Sunny",
                "bubu": "Bubu",
                "luna": "Luna",
                "tiko": "Tiko",
                "mino": "Mino",
                "koko": "Koko",
                "bugsbunny": "Conejo Divertido",
                "ironman": "Héroe de Metal",
                "peppapig": "Cerdito",
                "bluey": "Perro Azul",
                "pawpatrol": "Perros Rescatadores",
                "moana": "Soñadora del Océano",
                "mario": "Super Saltador",
                "shrek": "Gigante Verde",
                "pussinboots": "Gato Botas",
                "sid": "Amigo Helado",
                "dora": "Explorador Aventurero",
                "olaf": "Amigo Muñeco de Nieve",
                "pikachu": "Chispa Amarilla",
                "scoobydoo": "Cachorro Misterioso",
                "winnie": "Winnie",
                "bunny": "Conejo",
                "barbie": "Chica de Ensueño Rosa",
                "tractor": "Tractor",
                "mcqueen": "Corredor",
                "hulk": "Héroe Fuerte Verde"
            },
            "fr": {
                "spiderman": "Combattant Araignée",
                "minion": "Ami Jaune",
                "tweety": "Oiseau Gazouillant",
                "spongebob": "Bulle",
                "elsa": "Princesse des Glaces Elisa",
                "tom": "Chat Rusé Tim",
                "jerry": "Souris Maligne Herry",
                "ninjaturtles": "Héros Carapace",
                "sunny": "Sunny",
                "bubu": "Bubu",
                "luna": "Luna",
                "tiko": "Tiko",
                "mino": "Mino",
                "koko": "Koko",
                "bugsbunny": "Lapin Rigolo",
                "ironman": "Héros Métal",
                "peppapig": "Cochon",
                "bluey": "Chien Bleu",
                "pawpatrol": "Chiens Sauveteurs",
                "moana": "Rêveuse de l'Océan",
                "mario": "Super Sauteur",
                "shrek": "Géant Vert",
                "pussinboots": "Chat Bottes",
                "sid": "Ami Givré",
                "dora": "Explorateur Aventurier",
                "olaf": "Ami Bonhomme de Neige",
                "pikachu": "Étincelle Jaune",
                "scoobydoo": "Chiot Mystérieux",
                "winnie": "Winnie",
                "bunny": "Lapin",
                "barbie": "Fille de Rêve Rose",
                "tractor": "Tracteur",
                "mcqueen": "Coureur",
                "hulk": "Héros Fort Vert"
            },
            "pt": {
                "spiderman": "Lutador Aranha",
                "minion": "Amigo Amarelo",
                "tweety": "Pássaro Tagarela",
                "spongebob": "Bolha",
                "elsa": "Princesa do Gelo Elisa",
                "tom": "Gato Esperto Tom",
                "jerry": "Rato Inteligente Jerry",
                "ninjaturtles": "Heróis Casca",
                "sunny": "Sunny",
                "bubu": "Bubu",
                "luna": "Luna",
                "tiko": "Tiko",
                "mino": "Mino",
                "koko": "Koko",
                "bugsbunny": "Coelho Engraçado",
                "ironman": "Herói de Metal",
                "peppapig": "Porquinho",
                "bluey": "Cachorro Azul",
                "pawpatrol": "Cães Resgatadores",
                "moana": "Sonhadora do Oceano",
                "mario": "Super Saltador",
                "shrek": "Gigante Verde",
                "pussinboots": "Gato de Botas",
                "sid": "Amigo Gelado",
                "dora": "Exploradora Aventureira",
                "olaf": "Amigo Boneco de Neve",
                "pikachu": "Faísca Amarela",
                "scoobydoo": "Cachorrinho Misterioso",
                "winnie": "Winnie",
                "bunny": "Coelho",
                "barbie": "Menina Sonhadora Rosa",
                "tractor": "Trator",
                "mcqueen": "Corredor",
                "hulk": "Herói Forte Verde"
            }
        }
        
        # Get language-specific character name map, fallback to English
        character_display_map = character_display_maps.get(lang_key, character_display_maps["en"])
        character_name = character_display_map.get(character.lower(), character.capitalize())
        
        # Simple title if no child_name (no AI needed)
        if not child_name:
            # Translate topic
            topic_translations = {
                "tr": {"bedtime": "Uyku", "friendship": "Arkadaşlık", "sharing": "Paylaşma", "nutrition": "Beslenme"},
                "en": {"bedtime": "Bedtime", "friendship": "Friendship", "sharing": "Sharing", "nutrition": "Nutrition"},
                "de": {"bedtime": "Schlafenszeit", "friendship": "Freundschaft", "sharing": "Teilen", "nutrition": "Ernährung"},
                "es": {"bedtime": "Hora de Dormir", "friendship": "Amistad", "sharing": "Compartir", "nutrition": "Nutrición"},
                "fr": {"bedtime": "Coucher", "friendship": "Amitié", "sharing": "Partage", "nutrition": "Nutrition"},
                "pt": {"bedtime": "Hora de Dormir", "friendship": "Amizade", "sharing": "Compartilhar", "nutrition": "Nutrição"},
                "ar": {"bedtime": "وقت النوم", "friendship": "الصداقة", "sharing": "المشاركة", "nutrition": "التغذية"}
            }
            topic_map = topic_translations.get(lang_key, topic_translations["en"])
            topic_translated = topic_map.get(topic.lower() if topic else "bedtime", topic.replace('_', ' ').title() if topic else "Story")
            
            # Simple format: Character + Topic
            if lang_key == "tr":
                return f"{character_name}'nin {topic_translated} Hikayesi"
            elif lang_key == "de":
                return f"{character_name}s {topic_translated} Geschichte"
            elif lang_key == "es":
                return f"La Historia de {topic_translated} de {character_name}"
            elif lang_key == "fr":
                return f"L'Histoire de {topic_translated} de {character_name}"
            elif lang_key == "pt":
                return f"A História de {topic_translated} de {character_name}"
            elif lang_key == "ar":
                return f"قصة {topic_translated} مع {character_name}"
            else:  # en
                return f"{character_name}'s {topic_translated} Story"
        
        # Get first 500 characters of story for context (to avoid token limits)
        story_preview = story_text[:500] if len(story_text) > 500 else story_text
        
        # Language-specific instructions
        lang_instructions = {
            "tr": "Türkçe bir başlık oluştur. Kısa, çekici ve çocuk dostu olmalı. Maksimum 60 karakter.",
            "en": "Create an English title. Short, catchy, and child-friendly. Maximum 60 characters.",
            "de": "Erstelle einen deutschen Titel. Kurz, einprägsam und kindgerecht. Maximal 60 Zeichen.",
            "es": "Crea un título en español. Corto, atractivo y apropiado para niños. Máximo 60 caracteres.",
            "fr": "Créez un titre en français. Court, accrocheur et adapté aux enfants. Maximum 60 caractères.",
            "pt": "Crie um título em português. Curto, atraente e adequado para crianças. Máximo 60 caracteres.",
            "ar": "أنشئ عنواناً بالعربية. قصير وجذاب ومناسب للأطفال. الحد الأقصى 60 حرفاً."
        }
        
        lang_key = language[:2] if len(language) >= 2 else "en"
        instruction = lang_instructions.get(lang_key, lang_instructions["en"])
        
        # Language-specific title formats with child name
        title_formats = {
            "tr": [
                f'"{character_name} ve {child_name}\'nin [Topic] Macerası"',
                f'"{character_name} ile {child_name}\'nin [Topic] Hikayesi"'
            ],
            "en": [
                f'"{character_name} and {child_name}\'s [Topic] Adventure"',
                f'"{character_name} and {child_name}\'s [Topic] Story"'
            ],
            "de": [
                f'"{character_name} und {child_name}s [Topic] Abenteuer"',
                f'"{character_name} und {child_name}s [Topic] Geschichte"'
            ],
            "es": [
                f'"La Aventura de [Topic] de {character_name} y {child_name}"',
                f'"La Historia de [Topic] de {character_name} y {child_name}"'
            ],
            "fr": [
                f'"L\'Aventure de [Topic] de {character_name} et {child_name}"',
                f'"L\'Histoire de [Topic] de {character_name} et {child_name}"'
            ],
            "pt": [
                f'"A Aventura de [Topic] de {character_name} e {child_name}"',
                f'"A História de [Topic] de {character_name} e {child_name}"'
            ],
            "ar": [
                f'"مغامرة [Topic] مع {character_name} و {child_name}"',
                f'"قصة [Topic] مع {character_name} و {child_name}"'
            ]
        }
        
        # Build prompt
        title_format_examples = title_formats.get(lang_key, title_formats["en"])
        title_format_text = " or ".join(title_format_examples)
        
        child_name_requirement = f"""
CRITICAL - CHILD NAME IN TITLE: The story is personalized for a child named {child_name}. You MUST include the child's name ({child_name}) in the title. 
Use format like {title_format_text}.
The title MUST be personalized with the child's name - this is mandatory, not optional.""" if child_name else ""
        
        child_part = f" The story is personalized for a child named {child_name}." if child_name else ""
        
        # Language-specific topic translations for title generation
        # This ensures topic appears in the correct language in the title (e.g., "sharing" -> "paylaşma" in Turkish)
        topic_translations = {
            "tr": {
                "sharing": "paylaşma", "friendship": "arkadaşlık", "bedtime": "uyku", "confidence": "özgüven",
                "emotional_regulation": "duygusal düzenleme", "screen_time": "ekran süresi", "sibling": "kardeş",
                "imagination": "hayal gücü", "transitions": "geçiş", "kindness": "nezaket", "nutrition": "beslenme"
            },
            "en": {
                "sharing": "sharing", "friendship": "friendship", "bedtime": "bedtime", "confidence": "confidence",
                "emotional_regulation": "emotional regulation", "screen_time": "screen time", "sibling": "sibling",
                "imagination": "imagination", "transitions": "transitions", "kindness": "kindness", "nutrition": "nutrition"
            },
            "de": {
                "sharing": "teilen", "friendship": "freundschaft", "bedtime": "schlafenszeit", "confidence": "vertrauen",
                "emotional_regulation": "emotionale regulation", "screen_time": "bildschirmzeit", "sibling": "geschwister",
                "imagination": "fantasie", "transitions": "übergang", "kindness": "freundlichkeit", "nutrition": "ernährung"
            },
            "es": {
                "sharing": "compartir", "friendship": "amistad", "bedtime": "hora de dormir", "confidence": "confianza",
                "emotional_regulation": "regulación emocional", "screen_time": "tiempo de pantalla", "sibling": "hermano",
                "imagination": "imaginación", "transitions": "transición", "kindness": "bondad", "nutrition": "nutrición"
            },
            "fr": {
                "sharing": "partage", "friendship": "amitié", "bedtime": "coucher", "confidence": "confiance",
                "emotional_regulation": "régulation émotionnelle", "screen_time": "temps d'écran", "sibling": "frère",
                "imagination": "imagination", "transitions": "transition", "kindness": "gentillesse", "nutrition": "nutrition"
            },
            "pt": {
                "sharing": "compartilhar", "friendship": "amizade", "bedtime": "hora de dormir", "confidence": "confiança",
                "emotional_regulation": "regulação emocional", "screen_time": "tempo de tela", "sibling": "irmão",
                "imagination": "imaginação", "transitions": "transição", "kindness": "bondade", "nutrition": "nutrição"
            },
            "ar": {
                "sharing": "المشاركة", "friendship": "الصداقة", "bedtime": "وقت النوم", "confidence": "الثقة",
                "emotional_regulation": "التحكم العاطفي", "screen_time": "وقت الشاشة", "sibling": "الأخ",
                "imagination": "الخيال", "transitions": "الانتقال", "kindness": "اللطف", "nutrition": "التغذية"
            }
        }
        topic_map = topic_translations.get(lang_key, topic_translations["en"])
        topic_translated = topic_map.get(topic.lower() if topic else "", topic or "") if topic else ""
        topic_part = f" The story is about: {topic_translated}." if topic_translated else ""
        
        # Language guidance for title generation (age-appropriate, gentle instruction)
        # Note: For 2-8 year olds, we want natural, child-friendly titles in the correct language
        # Using gentle guidance rather than strict enforcement to allow creative, age-appropriate titles
        language_guidance = {
            "tr": "Please create the title in Turkish (Türkçe). Use Turkish grammar and vocabulary that is natural and appropriate for children aged 2-8.",
            "en": "Please create the title in English. Use English grammar and vocabulary that is natural and appropriate for children aged 2-8.",
            "de": "Please create the title in German (Deutsch). Use German grammar and vocabulary that is natural and appropriate for children aged 2-8.",
            "es": "Please create the title in Spanish (Español). Use Spanish grammar and vocabulary that is natural and appropriate for children aged 2-8.",
            "fr": "Please create the title in French (Français). Use French grammar and vocabulary that is natural and appropriate for children aged 2-8.",
            "pt": "Please create the title in Portuguese (Português). Use Portuguese grammar and vocabulary that is natural and appropriate for children aged 2-8.",
            "ar": "Please create the title in Arabic (العربية). Use Arabic grammar and vocabulary that is natural and appropriate for children aged 2-8."
        }
        lang_enforcement_text = language_guidance.get(lang_key, language_guidance["en"])
        
        prompt = f"""You are a children's story title generator. Create an engaging, child-friendly title for this story.

CRITICAL - CHARACTER NAME: The main character in this story is "{character_name}". You MUST use "{character_name}" in the title, NOT any other character names that might appear in the story text.

Character: {character_name}
{child_part}{topic_part}
Story preview: {story_preview}

Requirements:
1. {instruction}
2. {lang_enforcement_text}
3. The title MUST include the character name "{character_name}" - this is mandatory
4. The title should reflect the main theme or lesson of the story
5. It should be positive and appropriate for children aged 2-8
6. Do NOT use any other character names from the story text - ONLY use "{character_name}"{child_name_requirement}
7. Do NOT include quotes, colons, or special punctuation
8. Return ONLY the title, no explanations

Title:"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use mini for fast, cheap title generation
            messages=[
                {"role": "system", "content": "You are a children's story title generator. Return only the title, no explanations or quotes."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,  # Slightly higher for creativity, but still controlled
            max_tokens=30  # Just need the title
        )
        
        title = response.choices[0].message.content.strip()
        
        # Clean up title (remove quotes, extra whitespace)
        title = title.strip('"').strip("'").strip()
        
        # Validate length (max 60 characters)
        if len(title) > 60:
            title = title[:57] + "..."
        
        # Fallback if title is too short or empty
        if len(title) < 3:
            print(f"⚠️ [generate_story_title] Generated title too short: '{title}', using fallback")
            return extract_title_from_text(story_text)
        
        # Verify that the generated title uses the correct character name
        title_lower = title.lower()
        character_name_lower = character_name.lower()
        if character_name_lower not in title_lower:
            print(f"⚠️ [generate_story_title] WARNING: Generated title '{title}' does not contain character name '{character_name}'")
            print(f"   Character slug was: {character}, mapped to display name: {character_name}")
            # Try to regenerate with stronger emphasis on character name
            # For now, just log the warning - the title is still valid
        
        print(f"✅ [generate_story_title] Generated title: '{title}' (language: {language}, character: {character_name}, slug: {character})")
        return title
        
    except Exception as e:
        print(f"⚠️ [generate_story_title] Error generating title with AI: {e}, using fallback")
        return extract_title_from_text(story_text)


def extract_title_from_text(text: str) -> str:
    """Extract a title from story text (fallback method)."""
    # Use first sentence or first 50 characters
    first_line = text.split("\n")[0].strip()
    if len(first_line) > 50:
        return first_line[:47] + "..."
    return first_line


@app.get("/stories/{story_id}", response_model=StoryResponse)
async def get_story(
    story_id: str,
    user_id: Optional[str] = Depends(verify_firebase_token)
):
    """Get a single story by ID."""
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database unavailable")
        
        story_ref = db.collection("stories").document(story_id)
        story_doc = story_ref.get()
        
        if not story_doc.exists:
            raise HTTPException(status_code=404, detail="Story not found")
        
        story_data = story_doc.to_dict()
        
        # Verify ownership (skip for public stories)
        # CRITICAL: Public stories (is_public=True) are accessible to all users
        # Private stories require ownership verification
        is_public = story_data.get("is_public", False)
        story_owner = story_data.get("owner_user_id")
        
        if not is_public:
            # Private story: verify ownership
            if story_owner != user_id:
                print(f"⚠️ [GET /stories/{story_id}] Ownership verification failed (private story):")
                print(f"   Story owner_user_id: {story_owner}")
                print(f"   Request user_id: {user_id}")
                print(f"   is_public: {is_public}")
                raise HTTPException(status_code=403, detail="Access denied")
        else:
            # Public story: allow access to all authenticated users
            print(f"✅ [GET /stories/{story_id}] Public story access granted:")
            print(f"   Story owner_user_id: {story_owner}")
            print(f"   Request user_id: {user_id}")
            print(f"   is_public: {is_public}")
        
        # Log story data for debugging
        print(f"📖 [GET /stories/{story_id}] Story data from Firestore:")
        print(f"   id: {story_data.get('id', 'N/A')}")
        print(f"   title: {story_data.get('title', 'N/A')}")
        print(f"   status: {story_data.get('status', 'N/A')}")
        print(f"   character_id: {story_data.get('character_id', 'N/A')}")
        print(f"   language: {story_data.get('language', 'N/A')}")
        custom_desc = story_data.get('custom_description')
        if custom_desc:
            print(f"   custom_description: '{custom_desc}' (length: {len(custom_desc)} chars)")
        else:
            print(f"   custom_description: None")
        print(f"   All fields: {list(story_data.keys())}")
        
        # Debug: Log scenes array structure
        if "scenes" in story_data and story_data["scenes"]:
            scenes = story_data["scenes"]
            print(f"   📋 [GET /stories/{story_id}] Scenes array has {len(scenes)} scenes")
            if len(scenes) > 0:
                first_scene = scenes[0]
                print(f"   📋 [GET /stories/{story_id}] First scene keys: {list(first_scene.keys()) if isinstance(first_scene, dict) else 'Not a dict'}")
                if isinstance(first_scene, dict) and "audio_url" in first_scene:
                    print(f"   ✅ [GET /stories/{story_id}] First scene has audio_url: {first_scene.get('audio_url', 'N/A')}")
                else:
                    print(f"   ⚠️ [GET /stories/{story_id}] First scene does NOT have audio_url field")
        
        # Ensure all required fields are present
        if "character_id" not in story_data:
            print(f"⚠️ [GET /stories/{story_id}] Missing character_id, using default 'mino'")
            story_data["character_id"] = "mino"
        if "language" not in story_data:
            print(f"⚠️ [GET /stories/{story_id}] Missing language, using default 'en'")
            story_data["language"] = "en"
        
        # CRITICAL: Normalize text field - UI expects "text", not "generated_text"
        # Copy generated_text to text if text is missing
        if not story_data.get("text") and story_data.get("generated_text"):
            story_data["text"] = story_data["generated_text"]
        
        response = StoryResponse(**story_data)
        
        # Log response JSON
        import json as json_lib
        response_json = json_lib.dumps(response.dict(), ensure_ascii=False, default=str)
        print(f"📤 [GET /stories/{story_id}] Response JSON: {response_json}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching story: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stories", response_model=StoryListResponse)
async def list_stories(
    userId: str = "me",
    limit: int = 10,
    lang: Optional[str] = None,  # Optional language filter
    include_public: bool = True,  # Include public stories from other users
    user_id: Optional[str] = Depends(verify_firebase_token)
):
    """List user's stories and optionally public stories from other users.
    
    Args:
        userId: User ID (default "me" = current user)
        limit: Max number of stories to return
        lang: Optional language filter (e.g., "tr", "en", "de", "es", "fr")
              If provided, only stories in that language are returned.
              If not provided, all stories are returned.
        include_public: If True (default), include public stories from other users.
                       If False, only return user's own stories.
    
    NOTE: This endpoint requires Firestore composite indexes:
    
    1. For user's own stories:
       - Collection: stories
       - Fields: owner_user_id (Ascending), created_at (Descending), __name__ (Descending)
    
    2. For public stories (CRITICAL - required for Most Liked and Last Created sections):
       - Collection: stories
       - Fields: is_public (Ascending), status (Ascending), created_at (Descending), __name__ (Descending)
    
    If you see an index error, create it via Firebase Console or use the link in the error message.
    The error message includes a direct link to create the required index.
    """
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        if not db:
            return StoryListResponse(stories=[], quota_remaining=3)
        
        stories = []
        stories_ref = db.collection("stories")
        
        # Get user's own stories
        # NOTE: This query requires composite index: owner_user_id (Ascending) + created_at (Descending)
        user_query = stories_ref.where(filter=FieldFilter("owner_user_id", "==", user_id))\
                               .order_by("created_at", direction=firestore.Query.DESCENDING)\
                               .limit(limit)
        
        user_story_ids = set()
        for doc in user_query.stream():
            story_data = doc.to_dict()
            # Apply language filter if specified
            if lang:
                story_lang = story_data.get("language", "en")
                if story_lang != lang:
                    continue  # Skip stories in other languages
            
            # CRITICAL: Normalize text field - UI expects "text", not "generated_text"
            # Copy generated_text to text if text is missing (do this ONCE, before any checks)
            if not story_data.get("text") and story_data.get("generated_text"):
                story_data["text"] = story_data["generated_text"]
            
            # CRITICAL: For user's own stories, include all statuses (including generating ones)
            # But for ready stories, ensure they have text content (not placeholder)
            story_status = story_data.get("status")
            story_text = story_data.get("text") or story_data.get("generated_text")
            
            # Include all user stories (even if generating), but skip ready stories without text
            if story_status == "ready" and not story_text:
                continue  # Skip placeholder ready stories (not fully generated yet)
            
            story_data.setdefault("is_public", True)  # Default to public if missing
            stories.append(StoryResponse(**story_data))
            user_story_ids.add(doc.id)
        
        # Get public stories from other users (if include_public=True and we have space)
        # CRITICAL: This query requires a composite index:
        # - Collection: stories
        # - Fields: is_public (Ascending), status (Ascending), created_at (Descending), __name__ (Descending)
        # If index is missing, the error message will include a link to create it
        if include_public and len(stories) < limit:
            remaining_limit = limit - len(stories)
            try:
                # Get public stories (excluding user's own stories)
                public_query = stories_ref.where(filter=FieldFilter("is_public", "==", True))\
                                         .where(filter=FieldFilter("status", "==", "ready"))\
                                         .order_by("created_at", direction=firestore.Query.DESCENDING)\
                                         .limit(remaining_limit * 2)  # Get more to filter out user's stories
                
                for doc in public_query.stream():
                    if doc.id in user_story_ids:
                        continue  # Skip user's own stories (already included above)
                    
                    story_data = doc.to_dict()
                    # Apply language filter if specified
                    if lang:
                        story_lang = story_data.get("language", "en")
                        if story_lang != lang:
                            continue  # Skip stories in other languages
                    
                    # CRITICAL: Normalize text field - UI expects "text", not "generated_text"
                    # Copy generated_text to text if text is missing (do this BEFORE checking story_text)
                    if not story_data.get("text") and story_data.get("generated_text"):
                        story_data["text"] = story_data["generated_text"]
                    
                    # Only include ready public stories with generated text
                    # CRITICAL: Placeholder stories have status="ready" but no text/generated_text
                    # These should not be shown in HomeView until they are fully generated
                    story_status = story_data.get("status")
                    story_text = story_data.get("text") or story_data.get("generated_text")
                    
                    if story_status == "ready" and story_text:
                        story_data.setdefault("is_public", True)
                        stories.append(StoryResponse(**story_data))
                        if len(stories) >= limit:
                            break
            except Exception as e:
                # If index error, log it and continue without public stories
                error_msg = str(e)
                if "index" in error_msg.lower() or "requires an index" in error_msg.lower():
                    print(f"⚠️ [list_stories] Firestore index missing for public stories query. Error: {error_msg}")
                    print(f"   ℹ️ Public stories will not be included until the index is created.")
                    print(f"   ℹ️ Most Liked and Last Created sections will be empty until index is ready.")
                    # Continue without public stories (user's own stories will still be returned)
                else:
                    raise  # Re-raise if it's a different error
        
        # Sort all stories by created_at (most recent first)
        stories.sort(key=lambda s: s.created_at, reverse=True)
        stories = stories[:limit]  # Ensure we don't exceed limit
        
        # Get quota remaining
        has_entitlement = await check_user_entitlement(user_id)
        if has_entitlement:
            quota_remaining_value = None  # Unlimited for subscribers
        else:
            has_quota, quota_remaining = await check_user_quota(user_id, "quick")
            quota_remaining_value = quota_remaining if has_quota else 0
        
        # CRITICAL: Log response before returning (for debugging iOS decode errors)
        print(f"📤 [list_stories] Returning {len(stories)} stories for user {user_id}")
        print(f"   Language filter: {lang}")
        print(f"   Include public: {include_public}")
        print(f"   Has entitlement: {has_entitlement}")
        print(f"   Quota remaining: {quota_remaining_value}")
        if stories:
            print(f"   First story: id={stories[0].id}, title={stories[0].title[:50] if stories[0].title else 'N/A'}, status={stories[0].status}, is_public={stories[0].is_public}")
            print(f"   First story fields: character_id={stories[0].character_id}, language={stories[0].language}, owner_user_id={stories[0].owner_user_id}")
        
        return StoryListResponse(
            stories=stories,
            quota_remaining=quota_remaining_value
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error listing stories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/stories/{story_id}")
async def delete_story(
    story_id: str,
    user_id: Optional[str] = Depends(verify_firebase_token)
):
    """Delete a story by ID. Only the owner can delete their own story."""
    print(f"🗑️ [DELETE /stories/{story_id}] Delete request received")
    print(f"   User ID: {user_id}")
    print(f"   Story ID: {story_id}")
    
    try:
        if not user_id:
            print("❌ [DELETE] Authentication required")
            raise HTTPException(status_code=401, detail="Authentication required")
        
        if not db:
            print("❌ [DELETE] Database unavailable")
            raise HTTPException(status_code=500, detail="Database unavailable")
        
        story_ref = db.collection("stories").document(story_id)
        story_doc = story_ref.get()
        
        if not story_doc.exists:
            print(f"❌ [DELETE] Story not found: {story_id}")
            raise HTTPException(status_code=404, detail="Story not found")
        
        story_data = story_doc.to_dict()
        story_owner = story_data.get("owner_user_id")
        
        print(f"🔍 [DELETE] Ownership check:")
        print(f"   Story owner_user_id: {story_owner}")
        print(f"   Request user_id: {user_id}")
        
        # Verify ownership - CRITICAL: Only allow deletion of own stories
        if story_owner != user_id:
            print(f"❌ [DELETE] Access denied: Story belongs to {story_owner}, not {user_id}")
            raise HTTPException(status_code=403, detail="Access denied: You can only delete your own stories")
        
        # Additional safety check: Only allow deletion of custom stories
        story_kind = story_data.get("kind", "system")
        if story_kind != "custom":
            print(f"⚠️ [DELETE] Attempted to delete non-custom story (kind: {story_kind})")
            raise HTTPException(status_code=403, detail="Only custom stories can be deleted")
        
        # Delete the story document
        story_ref.delete()
        
        print(f"✅ [DELETE /stories/{story_id}] Story deleted successfully by user: {user_id}")
        
        return {"message": "Story deleted successfully", "story_id": story_id}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [DELETE] Error deleting story: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/stories/{story_id}/duplicate", response_model=CreateStoryResponse)
async def duplicate_story(
    story_id: str,
    request: DuplicateStoryRequest,
    user_id: Optional[str] = Depends(verify_firebase_token)
):
    """Duplicate a story with optional new character or length."""
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database unavailable")
        
        # Get original story
        story_ref = db.collection("stories").document(story_id)
        story_doc = story_ref.get()
        
        if not story_doc.exists:
            raise HTTPException(status_code=404, detail="Story not found")
        
        original_data = story_doc.to_dict()
        
        # Verify ownership
        if original_data.get("owner_user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Create new story request
        new_character = request.character_id or original_data.get("character_id", "mino")
        new_length = request.length or original_data.get("length_type", "quick")
        
        story_request = StoryRequest(
            topic=original_data.get("topic", ""),
            language=original_data.get("language", "en"),
            child_name=original_data.get("child_name"),
            character_id=new_character,
            length=new_length
        )
        
        # Create new story
        return await create_custom_story(story_request, user_id)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error duplicating story: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# MARK: - RevenueCat Webhook Handler
@app.post("/revenuecat/webhooks")
async def revenuecat_webhook(request: Request):
    """
    RevenueCat webhook handler
    Best Practice: Server-to-server notifications for subscription state changes
    
    Handles:
    - INITIAL_PURCHASE: First purchase
    - RENEWAL: Subscription renewed
    - CANCELLATION: Subscription cancelled
    - UNCANCELLATION: Cancellation reversed
    - EXPIRATION: Subscription expired
    - TRIAL_STARTED: Trial started
    - TRIAL_ENDED: Trial ended (converted to paid) - CRITICAL
    - BILLING_ISSUE: Payment issue (grace period)
    - PRODUCT_CHANGE: Product changed
    """
    try:
        # Get request body
        body = await request.body()
        body_json = json.loads(body)
        
        # Get event type
        event_type = body_json.get("event", {}).get("type")
        app_user_id = body_json.get("event", {}).get("app_user_id")
        product_id = body_json.get("event", {}).get("product_id")
        expiration_date = body_json.get("event", {}).get("expiration_at")
        
        print(f"📥 RevenueCat webhook received: {event_type} for user: {app_user_id}, product: {product_id}")
        
        # Handle different event types
        if event_type == "INITIAL_PURCHASE":
            # iOS BEST PRACTICE: Initial purchase (could be trial start or paid subscription)
            print(f"✅ Initial purchase: {product_id}, expires: {expiration_date}")
            # Update Firestore if needed
            if db and app_user_id:
                try:
                    expires_ms = int(datetime.fromisoformat(expiration_date.replace('Z', '+00:00')).timestamp() * 1000) if expiration_date else None
                    subscription_ref = db.collection("subscriptions").document(app_user_id)
                    subscription_ref.set({
                        "user_id": app_user_id,
                        "product_id": product_id,
                        "expires_date_ms": expires_ms,
                        "is_trial_period": False,  # Will be updated by TRIAL_STARTED event if trial
                        "will_renew": True,  # Active subscription will renew
                        "billing_issue": False,
                        "updated_at": firestore.SERVER_TIMESTAMP,
                        "updated_via": "revenuecat_webhook_initial_purchase"
                    }, merge=True)
                    print(f"✅ [Webhook] Firestore updated for user {app_user_id}: product={product_id}, expires_ms={expires_ms}")
                except Exception as e:
                    print(f"❌ [Webhook] Failed to update Firestore for INITIAL_PURCHASE: {e}")
            else:
                print(f"⚠️ [Webhook] Skipping Firestore update: db={db is not None}, app_user_id={app_user_id}")
                
        elif event_type == "RENEWAL":
            # iOS BEST PRACTICE: Subscription renewed successfully
            # Clear billing_issue and will_renew flags
            print(f"✅ Subscription renewed: {product_id}, expires: {expiration_date}")
            # Update Firestore
            if db and app_user_id:
                subscription_ref = db.collection("subscriptions").document(app_user_id)
                subscription_ref.set({
                    "user_id": app_user_id,
                    "product_id": product_id,
                    "expires_date_ms": int(datetime.fromisoformat(expiration_date.replace('Z', '+00:00')).timestamp() * 1000) if expiration_date else None,
                    "billing_issue": False,  # Payment successful
                    "will_renew": True,  # Subscription is active and will renew
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "updated_via": "revenuecat_webhook_renewal"
                }, merge=True)
                
        elif event_type == "CANCELLATION":
            print(f"⚠️ Subscription cancelled: {product_id}, expires: {expiration_date}")
            # Update Firestore (subscription will expire at end of period)
            if db and app_user_id:
                subscription_ref = db.collection("subscriptions").document(app_user_id)
                subscription_ref.set({
                    "user_id": app_user_id,
                    "product_id": product_id,
                    "cancelled": True,
                    "expires_date_ms": int(datetime.fromisoformat(expiration_date.replace('Z', '+00:00')).timestamp() * 1000) if expiration_date else None,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "updated_via": "revenuecat_webhook_cancellation"
                }, merge=True)
                
        elif event_type == "UNCANCELLATION":
            print(f"✅ Subscription uncancelled: {product_id}, expires: {expiration_date}")
            # Update Firestore
            if db and app_user_id:
                subscription_ref = db.collection("subscriptions").document(app_user_id)
                subscription_ref.set({
                    "user_id": app_user_id,
                    "product_id": product_id,
                    "cancelled": False,
                    "expires_date_ms": int(datetime.fromisoformat(expiration_date.replace('Z', '+00:00')).timestamp() * 1000) if expiration_date else None,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "updated_via": "revenuecat_webhook_uncancellation"
                }, merge=True)
                
        elif event_type == "EXPIRATION":
            print(f"❌ Subscription expired: {product_id}")
            # Update Firestore
            if db and app_user_id:
                subscription_ref = db.collection("subscriptions").document(app_user_id)
                subscription_ref.set({
                    "user_id": app_user_id,
                    "product_id": product_id,
                    "expired": True,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "updated_via": "revenuecat_webhook_expiration"
                }, merge=True)
                
        elif event_type == "TRIAL_STARTED":
            print(f"📅 Trial started: {product_id}, expires: {expiration_date}")
            # Update Firestore
            if db and app_user_id:
                subscription_ref = db.collection("subscriptions").document(app_user_id)
                subscription_ref.set({
                    "user_id": app_user_id,
                    "product_id": product_id,
                    "expires_date_ms": int(datetime.fromisoformat(expiration_date.replace('Z', '+00:00')).timestamp() * 1000) if expiration_date else None,
                    "is_trial_period": True,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "updated_via": "revenuecat_webhook_trial_started"
                }, merge=True)
                
        elif event_type == "TRIAL_ENDED":
            # CRITICAL: Trial ended, converted to paid subscription
            print(f"✅ Trial ended, converted to paid: {product_id}, expires: {expiration_date}")
            # Update Firestore
            if db and app_user_id:
                subscription_ref = db.collection("subscriptions").document(app_user_id)
                subscription_ref.set({
                    "user_id": app_user_id,
                    "product_id": product_id,
                    "expires_date_ms": int(datetime.fromisoformat(expiration_date.replace('Z', '+00:00')).timestamp() * 1000) if expiration_date else None,
                    "is_trial_period": False,  # Trial bitti, artık paid
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "updated_via": "revenuecat_webhook_trial_ended"
                }, merge=True)
                print(f"✅ Firestore updated for trial-to-paid conversion: {app_user_id}")
                
        elif event_type == "BILLING_ISSUE":
            # iOS BEST PRACTICE: Grace period handling
            # RevenueCat automatically enters grace period (default 16 days) when payment fails
            # User should continue to have access during grace period
            print(f"⚠️ Billing issue: {product_id} (grace period - user retains access)")
            # Update Firestore with willRenew=True to indicate grace period
            if db and app_user_id:
                subscription_ref = db.collection("subscriptions").document(app_user_id)
                subscription_ref.set({
                    "user_id": app_user_id,
                    "product_id": product_id,
                    "billing_issue": True,
                    "will_renew": True,  # RevenueCat will retry payment, user keeps access
                    "expires_date_ms": int(datetime.fromisoformat(expiration_date.replace('Z', '+00:00')).timestamp() * 1000) if expiration_date else None,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "updated_via": "revenuecat_webhook_billing_issue"
                }, merge=True)
                
        elif event_type == "PRODUCT_CHANGE":
            previous_product_id = body_json.get("event", {}).get("previous_product_id")
            print(f"🔄 Product changed: {previous_product_id} → {product_id}")
            # Update Firestore
            if db and app_user_id:
                subscription_ref = db.collection("subscriptions").document(app_user_id)
                subscription_ref.set({
                    "user_id": app_user_id,
                    "product_id": product_id,
                    "previous_product_id": previous_product_id,
                    "expires_date_ms": int(datetime.fromisoformat(expiration_date.replace('Z', '+00:00')).timestamp() * 1000) if expiration_date else None,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "updated_via": "revenuecat_webhook_product_change"
                }, merge=True)
        
        # Always return 200 OK to acknowledge receipt
        return {"status": "ok", "event_type": event_type}
        
    except Exception as e:
        print(f"❌ Error handling RevenueCat webhook: {e}")
        import traceback
        traceback.print_exc()
        # Still return 200 to prevent retries for invalid requests
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
