"""Audio conversion utilities."""

import os
import tempfile
import subprocess
from typing import Optional


async def convert_mp3_to_wav(mp3_data: bytes) -> bytes:
    """Convert MP3 audio data to WAV format using ffmpeg.
    
    Args:
        mp3_data: MP3 audio data as bytes
        
    Returns:
        WAV audio data as bytes, or original MP3 data if conversion fails
    """
    try:
        # Create temporary files
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as mp3_file:
            mp3_file.write(mp3_data)
            mp3_path = mp3_file.name
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file:
            wav_path = wav_file.name
        
        try:
            # Use ffmpeg to convert MP3 to WAV
            subprocess.run(
                ['ffmpeg', '-i', mp3_path, '-y', '-ar', '22050', '-ac', '1', '-f', 'wav', wav_path],
                check=True,
                capture_output=True
            )
            
            # Read WAV file
            with open(wav_path, 'rb') as f:
                wav_data = f.read()
            
            return wav_data
        finally:
            # Clean up temporary files
            try:
                os.unlink(mp3_path)
                os.unlink(wav_path)
            except:
                pass
    except Exception as e:
        print(f"⚠️ FFmpeg conversion failed: {e}")
        # Fallback: return MP3 as-is (some players can handle MP3)
        return mp3_data
