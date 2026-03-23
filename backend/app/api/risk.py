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


@router.get("/gate-diagnostics")
async def get_gate_diagnostics() -> dict:
    """Return current state of all pre-trade gate checks and feature flags.

    This endpoint is intended for monitoring dashboards and n8n observability
    nodes.  It shows which gates are active and what their current settings are
    so that blocked decisions can be diagnosed without log scraping.
    """
    from app.core.feature_flags import (
        ingestion_hardening_enabled,
        options_signals_enabled,
        strict_freshness_enabled,
        walk_forward_gate_enabled,
    )
    from app.risk.pre_trade_checks import _DEFAULT_DATA_MAX_AGE_SECONDS, _ENTRY_CUTOFF
    from app.risk.tail_risk import TAIL_RISK_BLOCK_THRESHOLD

    return {
        "feature_flags": {
            "ingestion_hardening": ingestion_hardening_enabled(),
            "options_signals": options_signals_enabled(),
            "walk_forward_gate": walk_forward_gate_enabled(),
            "strict_freshness": strict_freshness_enabled(),
        },
        "gates": {
            "stale_data_max_age_seconds": _DEFAULT_DATA_MAX_AGE_SECONDS,
            "stale_data_hard_block_when": "FEATURE_STRICT_FRESHNESS=true",
            "entry_cutoff_time": str(_ENTRY_CUTOFF),
            "tail_risk_block_threshold": TAIL_RISK_BLOCK_THRESHOLD,
            "walk_forward_required_when": "FEATURE_WALK_FORWARD_GATE=true",
        },
    }


@router.get("/bot-counters")
async def get_bot_counters() -> dict:
    """Return accumulated gate-block counters from the bot manager.

    Useful for observing how many cycles were blocked by freshness, close-window,
    or model-validation gates since the last restart.
    """
    from app.services.bot_manager import bot_manager

    stats = bot_manager.get_statistics()
    return {
        "total_cycles": stats.get("total_cycles", 0),
        "total_orders": stats.get("total_orders", 0),
        "errors": stats.get("errors", 0),
        "stale_data_blocks": stats.get("stale_data_blocks", 0),
        "close_window_blocks": stats.get("close_window_blocks", 0),
        "model_validation_blocks": stats.get("model_validation_blocks", 0),
    }
