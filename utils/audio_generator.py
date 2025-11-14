"""Audio generation utilities."""

import struct


def generate_silent_audio(duration_seconds: float = 1.0, sample_rate: int = 44100) -> bytes:
    """Generate a silent WAV audio file.
    
    Args:
        duration_seconds: Duration of silent audio in seconds
        sample_rate: Sample rate (default: 44100 Hz)
        
    Returns:
        WAV file data as bytes (stereo, 16-bit PCM)
    """
    num_samples = int(sample_rate * duration_seconds)
    
    # WAV header for 44.1kHz stereo 16-bit
    wav_header = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + num_samples * 4,  # File size - 8
        b'WAVE',
        b'fmt ',
        16,  # fmt chunk size
        1,   # PCM format
        2,   # stereo
        sample_rate,
        sample_rate * 4,  # byte rate
        4,   # block align
        16,  # bits per sample
        b'data',
        num_samples * 4   # data size
    )
    
    # Silent audio data (zeros)
    silent_data = b'\x00' * (num_samples * 4)  # 2 channels * 2 bytes per sample
    
    return wav_header + silent_data
