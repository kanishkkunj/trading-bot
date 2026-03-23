"""Trading parameters API.

Stores and retrieves runtime-tunable trading parameters against the active
StrategyConfig record in the database (parameters JSON column).
Infrastructure settings (DB URL, API keys) remain in app.config.Settings — this
router is only for trading-logic parameters (thresholds, sizing, limits).

Endpoints
---------
GET  /              return current trading params (merged with defaults)
POST /              update params (partial update — only supplied keys change)
GET  /defaults      return factory defaults without touching the DB
POST /reset         reset active strategy params back to factory defaults
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.strategy import StrategyConfig

router = APIRouter()

# Factory defaults matching the validated Config 21 equity setup and workflow thresholds.
# All keys use snake_case to align with pydantic conventions.
DEFAULT_TRADING_PARAMS: Dict[str, Any] = {
    # Signal / ML gating
    "ensemble_threshold": 0.5,
    "rsi_threshold": 45,
    "sma_period": 50,
    "strategy_mode": "hybrid",      # trend_following | mean_reversion | hybrid
    "use_regime_filter": True,
    "trend_bias_boost": 0.03,
    "mean_reversion_bias_boost": 0.02,
    "regime_confidence_floor": 0.55,
    "volume_filter": False,
    # Risk management
    "risk_per_trade": 0.01,          # 1 % per trade
    "daily_loss_limit": -0.02,       # -2 % kill-switch
    "max_leverage": 2.0,
    "max_positions": 3,
    "paper_capital": 500.0,
    # Exit rules
    "stop_loss_atr_mult": 1.0,
    "take_profit_atr_mult": 2.5,
    "max_hold_days": 5,
    # Automation flags
    "bot_enabled": True,
    "auto_execute": True,
    "auto_log": True,
}


async def _get_active_strategy(db: AsyncSession) -> Optional[StrategyConfig]:
    result = await db.execute(
        select(StrategyConfig).where(StrategyConfig.is_active.is_(True))
    )
    return result.scalar_one_or_none()


@router.get("/")
async def get_trading_params(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Return current trading parameters merged with factory defaults.

    If no active strategy exists the defaults are returned directly.
    """
    strategy = await _get_active_strategy(db)
    if not strategy:
        return DEFAULT_TRADING_PARAMS.copy()
    return {**DEFAULT_TRADING_PARAMS, **(strategy.parameters or {})}


@router.post("/")
async def update_trading_params(
    params: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Partially update trading parameters on the active strategy.

    Only keys present in the request body are changed; others keep their
    current values.  Returns the full merged parameter set.
    """
    strategy = await _get_active_strategy(db)
    if not strategy:
        raise HTTPException(
            status_code=404,
            detail="No active strategy found. Create one first via POST /api/v1/strategy/.",
        )
    current: Dict[str, Any] = dict(strategy.parameters or {})
    current.update(params)
    strategy.parameters = current
    await db.commit()
    await db.refresh(strategy)
    return {**DEFAULT_TRADING_PARAMS, **strategy.parameters}


@router.get("/defaults")
async def get_default_params() -> Dict[str, Any]:
    """Return factory default trading parameters without modifying the database."""
    return DEFAULT_TRADING_PARAMS.copy()


@router.post("/reset")
async def reset_trading_params(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Reset active strategy parameters back to factory defaults."""
    strategy = await _get_active_strategy(db)
    if not strategy:
        raise HTTPException(
            status_code=404,
            detail="No active strategy found.",
        )
    strategy.parameters = DEFAULT_TRADING_PARAMS.copy()
    await db.commit()
    await db.refresh(strategy)
    return strategy.parameters
