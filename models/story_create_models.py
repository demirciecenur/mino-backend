"""Story creation-related Pydantic models."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class StoryRequest(BaseModel):
    """Request model for creating a new story."""
    topic: str = Field(..., description="Canonical story topic slug (e.g., 'sibling', 'bedtime', 'emotional_regulation')")
    custom_description: Optional[str] = Field(
        None,
        description="Optional free-form description from parent about the child's situation (any language)"
    )
    language: str = Field(default="en", description="Language code (en, tr, de, etc.)")
    child_name: Optional[str] = Field(None, description="Optional child's name to include in story")
    character_id: str = Field(..., description="Character ID (mino, luna, tiko, etc.)")
    length: str = Field(..., description="Story length: quick (2-3m) or dreamy (4-8m)")


class CreateStoryResponse(BaseModel):
    """Response model for story creation."""
    story_id: str
    status: str
    quota_remaining: Optional[int] = None


class StoryResponse(BaseModel):
    """Response model for a single story."""
    id: str
    title: str
    text: Optional[str] = None
    audio_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    status: str
    character_id: str = "mino"  # Default to "mino" if missing
    language: str = "en"  # Default to "en" if missing
    owner_user_id: str
    created_at: float  # Unix timestamp
    cover_url: Optional[str] = None
    quota_counted: bool = False
    topic: Optional[str] = None
    child_name: Optional[str] = None
    length_type: Optional[str] = None
    custom_description: Optional[str] = None  # Parent conversation text / custom description
    scenes: Optional[List[Dict[str, Any]]] = None  # Scenes array from Firestore (optional for backward compatibility)


class StoryListResponse(BaseModel):
    """Response model for listing stories."""
    stories: List[StoryResponse]
    quota_remaining: Optional[int] = None


class DuplicateStoryRequest(BaseModel):
    """Request model for duplicating a story."""
    character_id: Optional[str] = None
    length: Optional[str] = None

