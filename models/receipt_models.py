"""Receipt verification-related Pydantic models."""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class ReceiptRequest(BaseModel):
    """Request model for receipt verification."""
    receipt_data: str  # Base64 encoded receipt data
    user_id: Optional[str] = None  # Firebase user ID for tracking


class ReceiptResponse(BaseModel):
    """Response model for receipt verification."""
    valid: bool
    status: int  # Apple receipt status code
    environment: Optional[str] = None  # "Sandbox" or "Production"
    expires_date_ms: Optional[int] = None  # Subscription expiration timestamp
    trial_end_date_ms: Optional[int] = None  # Trial end timestamp
    is_trial_period: Optional[bool] = None
    is_in_intro_offer_period: Optional[bool] = None
    product_id: Optional[str] = None
    message: Optional[str] = None  # Error or info message
