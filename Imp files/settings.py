from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/settings", tags=["settings"])

class StrategyConfig(BaseModel):
    ensembleThreshold: float = 0.5
    rsiThreshold: int = 45
    smaPeriod: int = 50
    volumeFilter: bool = False

class RiskManagement(BaseModel):
    paperCapital: float = 500
    liveCapital: float = 1000
    riskPerTrade: float = 0.01  # 1%
    dailyLossLimit: float = -0.02  # -2%
    maxLeverage: float = 2.0
    maxPositions: int = 3

class AutomationSettings(BaseModel):
    botEnabled: bool = True
    autoExecute: bool = True
    autoLog: bool = True
    emailAlerts: bool = True

class SettingsUpdate(BaseModel):
    strategyConfig: StrategyConfig
    riskManagement: RiskManagement
    automation: AutomationSettings

# Global settings storage (in production, use database)
current_settings = {
    "strategyConfig": {
        "ensembleThreshold": 0.5,
        "rsiThreshold": 45,
        "smaPeriod": 50,
        "volumeFilter": False
    },
    "riskManagement": {
        "paperCapital": 500,
        "liveCapital": 1000,
        "riskPerTrade": 0.01,
        "dailyLossLimit": -0.02,
        "maxLeverage": 2,
        "maxPositions": 3
    },
    "automation": {
        "botEnabled": True,
        "autoExecute": True,
        "autoLog": True,
        "emailAlerts": True
    }
}

@router.get("")
async def get_settings():
    """Get current settings"""
    return current_settings

@router.post("/update")
async def update_settings(settings: SettingsUpdate):
    """Update settings"""
    global current_settings
    current_settings = {
        "strategyConfig": settings.strategyConfig.dict(),
        "riskManagement": settings.riskManagement.dict(),
        "automation": settings.automation.dict()
    }
    return {
        "status": "success",
        "message": "Settings updated successfully",
        "settings": current_settings
    }

@router.get("/strategy")
async def get_strategy_config():
    """Get strategy configuration"""
    return current_settings["strategyConfig"]

@router.post("/strategy/update")
async def update_strategy(config: StrategyConfig):
    """Update strategy configuration"""
    global current_settings
    current_settings["strategyConfig"] = config.dict()
    return {
        "status": "success",
        "message": "Strategy configuration updated",
        "config": current_settings["strategyConfig"]
    }

@router.get("/risk")
async def get_risk_config():
    """Get risk management configuration"""
    return current_settings["riskManagement"]

@router.post("/risk/update")
async def update_risk(config: RiskManagement):
    """Update risk management"""
    global current_settings
    current_settings["riskManagement"] = config.dict()
    return {
        "status": "success",
        "message": "Risk management updated",
        "config": current_settings["riskManagement"]
    }

@router.get("/automation")
async def get_automation_settings():
    """Get automation settings"""
    return current_settings["automation"]

@router.post("/automation/update")
async def update_automation(config: AutomationSettings):
    """Update automation settings"""
    global current_settings
    current_settings["automation"] = config.dict()
    return {
        "status": "success",
        "message": "Automation settings updated",
        "config": current_settings["automation"]
    }
