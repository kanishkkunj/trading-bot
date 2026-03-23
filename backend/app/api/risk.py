"""Risk management API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db

router = APIRouter()


@router.get("/status")
async def get_risk_status(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get current risk status (single user)."""
    # TODO: Implement full risk manager in Sprint 3
    return {
        "status": "healthy",
        "daily_loss_limit": 2.0,
        "current_daily_loss": 0.0,
        "daily_loss_pct": 0.0,
        "max_positions": 5,
        "current_positions": 0,
        "kill_switch_active": False,
        "circuit_breakers": {
            "slippage": False,
            "rejection_rate": False,
            "drawdown": False,
        },
    }


@router.get("/limits")
async def get_risk_limits(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get risk limits configuration (single user)."""
    return {
        "max_daily_loss_pct": 2.0,
        "max_risk_per_trade_pct": 0.5,
        "max_concurrent_positions": 5,
        "max_sector_concentration_pct": 40.0,
        "position_sizing": "atr",
        "circuit_breaker_slippage_pct": 1.0,
        "circuit_breaker_rejection_count": 3,
        "auto_kill_on_drawdown_pct": 5.0,
    }


@router.post("/kill-switch")
async def toggle_kill_switch(
    active: bool,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Toggle the kill switch (single user)."""
    # TODO: Implement kill switch in Sprint 3
    return {
        "status": "not_implemented",
        "message": "Kill switch coming in Sprint 3",
        "requested_state": active,
    }
