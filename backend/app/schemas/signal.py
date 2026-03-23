"""Signal schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.signal import SignalAction, SignalStatus


class SignalBase(BaseModel):
    """Base signal schema."""

    symbol: str = Field(..., min_length=1, max_length=20)
    action: SignalAction
    confidence: float = Field(..., ge=0, le=1)


class SignalCreate(SignalBase):
    """Signal creation schema."""

    suggested_quantity: Optional[int] = Field(None, gt=0)
    suggested_price: Optional[float] = Field(None, gt=0)
    model_version: str
    features_used: Optional[str] = None
    valid_until: Optional[datetime] = None


class SignalResponse(SignalBase):
    """Signal response schema."""

    id: str
    suggested_quantity: Optional[int]
    suggested_price: Optional[float]
    model_version: str
    features_used: Optional[str]
    status: SignalStatus
    status_reason: Optional[str]
    order_id: Optional[str]
    created_at: datetime
    valid_until: Optional[datetime]
    executed_at: Optional[datetime]

    class Config:
        from_attributes = True


class SignalListResponse(BaseModel):
    """Signal list response schema."""

    signals: list[SignalResponse]
    total: int
    page: int
    page_size: int


class SignalFilter(BaseModel):
    """Signal filter schema."""

    symbol: Optional[str] = None
    action: Optional[SignalAction] = None
    status: Optional[SignalStatus] = None
    min_confidence: Optional[float] = Field(None, ge=0, le=1)
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
