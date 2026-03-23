"""Bot control endpoints — start/stop the autonomous paper trading loop.

Routes (all prefixed with /api/v1/bot in main.py)
---------------------------------------------------
POST   /start            — start the trading bot
POST   /stop             — stop the trading bot
GET    /status           — is bot running, since when, with what config
GET    /statistics       — cumulative trading stats (cycles, orders, errors)
GET    /alerts           — recent alert log (?limit=20)
POST   /config/update    — change config of a running bot
GET    /health           — simple liveness check for monitoring / n8n polling
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.bot_manager import bot_manager

router = APIRouter()


# --------------------------------------------------------------------- schemas

class BotStartRequest(BaseModel):
    interval_seconds: int = Field(default=60, ge=5, description="Seconds between trading cycles")
    top_k: int = Field(default=5, ge=1, le=50, description="Max number of signals to act on per cycle")
    user_id: Optional[int] = Field(default=1, description="User context for paper trades")


class BotConfigUpdateRequest(BaseModel):
    interval_seconds: Optional[int] = Field(default=None, ge=5)
    top_k: Optional[int] = Field(default=None, ge=1, le=50)


# --------------------------------------------------------------------- endpoints

@router.post("/start", summary="Start the paper trading bot")
async def start_bot(body: BotStartRequest = BotStartRequest()) -> Dict[str, Any]:
    config = body.model_dump(exclude_none=True)
    result = bot_manager.start_bot(config=config)
    return result


@router.post("/stop", summary="Stop the paper trading bot")
async def stop_bot() -> Dict[str, Any]:
    result = bot_manager.stop_bot()
    return result


@router.get("/status", summary="Current bot state")
async def get_status() -> Dict[str, Any]:
    return bot_manager.get_status()


@router.get("/statistics", summary="Cumulative trading loop counters")
async def get_statistics() -> Dict[str, Any]:
    return bot_manager.get_statistics()


@router.get("/alerts", summary="Recent alert log")
async def get_alerts(
    limit: int = Query(default=20, ge=1, le=200, description="Number of recent alerts to return"),
) -> Dict[str, Any]:
    alerts = bot_manager.get_alerts(limit=limit)
    return {"count": len(alerts), "alerts": alerts}


@router.post("/config/update", summary="Update bot configuration at runtime")
async def update_config(body: BotConfigUpdateRequest) -> Dict[str, Any]:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updated = bot_manager.update_config(updates)
    return {"status": "updated", "config": updated}


@router.get("/health", summary="Liveness check — usable from n8n HTTP node")
async def health_check() -> Dict[str, Any]:
    status = bot_manager.get_status()
    return {
        "ok": True,
        "bot_running": status["is_running"],
        "started_at": status["started_at"],
    }
