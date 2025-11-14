"""Notification-related Pydantic models."""

from pydantic import BaseModel, Field
from typing import Optional


class StoryCompletedRequest(BaseModel):
    """Request model for story completion event."""
    child_id: str = Field(..., description="Child user ID")
    story_id: Optional[str] = Field(None, description="Story ID")
    topic: str = Field(..., description="Story topic")
    character: str = Field(..., description="Character name")
    language: str = Field("en", description="Language code")
    timestamp: Optional[float] = Field(None, description="Unix timestamp (optional, defaults to now)")
    child_name: Optional[str] = Field(None, description="Child name for personalization (optional, defaults to 'your child')")


class StoryCompletedResponse(BaseModel):
    """Response model for story completion event."""
    success: bool
    event_id: Optional[str] = None
    message: str


class DeviceRegistrationRequest(BaseModel):
    """Request model for device token registration."""
    parent_id: str = Field(..., description="Parent user ID")
    device_token: str = Field(..., description="FCM device token")
    notification_consent: bool = Field(True, description="Parent consent for notifications")


class DeviceRegistrationResponse(BaseModel):
    """Response model for device token registration."""
    success: bool
    message: str


class BadgeUnlockedRequest(BaseModel):
    """Request model for badge unlock event."""
    parent_id: str = Field(..., description="Parent user ID")
    badge_id: str = Field(..., description="Badge ID")
    badge_name: str = Field(..., description="Badge display name")
    badge_icon: str = Field(..., description="Badge icon emoji")
    language: str = Field("en", description="Language code")
    timestamp: Optional[float] = Field(None, description="Unix timestamp")
    child_name: Optional[str] = Field(None, description="Child name for personalization (optional, defaults to 'your child')")


class BadgeUnlockedResponse(BaseModel):
    """Response model for badge unlock event."""
    success: bool
    message: str


class StreakUpdatedRequest(BaseModel):
    """Request model for streak update event."""
    parent_id: str = Field(..., description="Parent user ID")
    streak_days: int = Field(..., description="Current streak days")
    language: str = Field("en", description="Language code")
    timestamp: Optional[float] = Field(None, description="Unix timestamp")
    child_name: Optional[str] = Field(None, description="Child name for personalization (optional, defaults to 'your child')")


class StreakUpdatedResponse(BaseModel):
    """Response model for streak update event."""
    success: bool
    message: str

