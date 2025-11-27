"""Story creation-related Pydantic models."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class StoryRequest(BaseModel):
    """Request model for creating a new story."""
    topic: str = Field(..., description="Story topic/prompt from parent")
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
    character_id: str
    language: str
    owner_user_id: str
    created_at: float  # Unix timestamp
    cover_url: Optional[str] = None
    quota_counted: bool = False
    topic: Optional[str] = None
    child_name: Optional[str] = None
    length_type: Optional[str] = None


class StoryListResponse(BaseModel):
    """Response model for listing stories."""
    stories: List[StoryResponse]
    quota_remaining: Optional[int] = None


class DuplicateStoryRequest(BaseModel):
    """Request model for duplicating a story."""
    character_id: Optional[str] = None
    length: Optional[str] = None

