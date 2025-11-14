"""Video composition-related Pydantic models."""

from pydantic import BaseModel
from typing import Optional


class ComposeRequest(BaseModel):
    """Request model for video composition."""
    base_video_uri: str
    audio_url: str
    session_id: str
    user_id: str


class ComposeResponse(BaseModel):
    """Response model for video composition."""
    video_url: str


class VideoGenerationRequest(BaseModel):
    """Request model for video generation."""
    character_name: str
    action: str
    profile_image_path: Optional[str] = None


class VideoGenerationResponse(BaseModel):
    """Response model for video generation."""
    video_url: Optional[str] = None
    video_path: Optional[str] = None
    success: bool
    message: str
