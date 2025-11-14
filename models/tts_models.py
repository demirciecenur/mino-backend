"""TTS-related Pydantic models."""

from pydantic import BaseModel
from typing import Optional


class TTSRequest(BaseModel):
    """Request model for TTS generation."""
    text: str
    style: dict
    lang: str
    character: Optional[str] = "mino"
    topic: Optional[str] = None
    scene_index: Optional[int] = None


class TTSResponse(BaseModel):
    """Response model for TTS generation."""
    audioUrl: str
