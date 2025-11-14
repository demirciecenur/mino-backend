"""Story composition-related Pydantic models."""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any


class StoryScene(BaseModel):
    id: str
    type: Literal[
        "opening",
        "narration",
        "question",
        "listen",
        "instruction",
        "followup",
        "encouragement",
        "closing",
        "closure",
    ]
    videoKey: Optional[Literal[
        "idle", "speak", "listen", "wave",
        "wave_greeting", "wave_goodbye",
        "talking", "storytelling",
        "side_glance", "raise_hand",
        "lean_closer", "hand_on_hip", "foot_tap"
    ]] = None
    text: str
    cues: Optional[List[Dict[str, Any]]] = None


class ComposedStory(BaseModel):
    id: str
    character: str
    topic: str
    language: str
    durationMinutes: Optional[int] = None
    age_range: str = Field(default="2-8")
    emotions: List[str] = Field(default_factory=list)
    scenes: List[StoryScene]


class ComposeStoryRequest(BaseModel):
    character: str
    topic: str
    lang: str = Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    overwrite: bool = False
    durationMinutes: Optional[int] = None


class ComposeStoryResponse(BaseModel):
    path: str
    created: bool
    story_id: str

