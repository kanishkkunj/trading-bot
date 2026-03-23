from fastapi import APIRouter
from typing import Optional, Dict
try:
    from backend.services.bot_manager import bot_manager
except ModuleNotFoundError as exc:
    if exc.name != "backend":
        raise
    from services.bot_manager import bot_manager

router = APIRouter(prefix="/api/bot", tags=["bot"])

@router.post("/start")
async def start_bot(config: Optional[Dict] = None):
    """Start the autonomous trading bot"""
    return bot_manager.start_bot(config=config)

@router.post("/stop")
async def stop_bot():
    """Stop the autonomous trading bot"""
    return bot_manager.stop_bot()

@router.get("/status")
async def get_bot_status():
    """Get current bot status"""
    return bot_manager.get_status()

@router.get("/statistics")
async def get_bot_statistics():
    """Get bot trading statistics"""
    return bot_manager.get_statistics()

@router.get("/alerts")
async def get_bot_alerts(limit: int = 20):
    """Get recent bot alerts"""
    return {
        "alerts": bot_manager.get_alerts(limit=limit),
        "total_alerts": len(bot_manager.get_alerts(limit=1000))
    }

@router.post("/config/update")
async def update_bot_config(config: Dict):
    """Update bot configuration"""
    return bot_manager.update_config(config)

@router.get("/health")
async def bot_health():
    """Check bot health"""
    status = bot_manager.get_status()
    is_healthy = status.get("is_running", False)
    
    return {
        "healthy": is_healthy,
        "status": status,
        "timestamp": datetime.now().isoformat()
    }

# Import datetime for timestamp
from datetime import datetime
