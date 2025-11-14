"""LLM-related Pydantic models."""

from pydantic import BaseModel


class LLMRequest(BaseModel):
    """Request model for LLM generation."""
    template: str
    vars: dict


class LLMResponse(BaseModel):
    """Response model for LLM generation."""
    text: str
