"""Signals API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.signal import SignalAction, SignalStatus
from app.schemas.signal import (
    SignalCreate,
    SignalResponse,
    SignalListResponse,
)
from app.services.signal_service import SignalService

router = APIRouter()


@router.post("/", response_model=SignalResponse, status_code=status.HTTP_201_CREATED)
async def create_signal(
    signal_data: SignalCreate,
    db: AsyncSession = Depends(get_db),
) -> SignalResponse:
    """Create a new trading signal for single user."""
    signal_service = SignalService(db)
    signal = await signal_service.create_signal(signal_data)
    return SignalResponse.model_validate(signal)


@router.get("/", response_model=SignalListResponse)
async def list_signals(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    symbol: Optional[str] = None,
    action: Optional[SignalAction] = None,
    status: Optional[SignalStatus] = None,
    min_confidence: Optional[float] = Query(default=None, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
) -> SignalListResponse:
    """List trading signals for single user."""
    signal_service = SignalService(db)
    signals = await signal_service.get_signals(
        skip=skip,
        limit=limit,
        symbol=symbol,
        action=action,
        status=status,
        min_confidence=min_confidence,
    )
    total = await signal_service.get_signal_count()
    return SignalListResponse(
        signals=[SignalResponse.model_validate(s) for s in signals],
        total=total,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
    )


@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal(
    signal_id: str,
    db: AsyncSession = Depends(get_db),
) -> SignalResponse:
    """Get a specific signal for single user."""
    signal_service = SignalService(db)
    signal = await signal_service.get_signal(signal_id)
    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signal not found",
        )
    return SignalResponse.model_validate(signal)


@router.post("/{signal_id}/execute")
async def execute_signal(
    signal_id: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
) -> SignalResponse:
    """Mark a signal as executed for single user."""
    signal_service = SignalService(db)
    signal = await signal_service.update_signal_status(
        signal_id, SignalStatus.EXECUTED, order_id=order_id
    )
    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signal not found",
        )
    return SignalResponse.model_validate(signal)
