"""Strategy API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.strategy import StrategyConfig
from app.strategy import ClaudeDecisionService, SignalScorer
from app.engine.model import MLModel
from app.llm_reasoning import ClaudeReasoner

router = APIRouter()


@router.get("/")
async def list_strategies(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List all strategies for single user."""
    result = await db.execute(select(StrategyConfig))
    strategies = result.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "version": s.version,
            "is_active": s.is_active,
            "is_default": s.is_default,
            "model_version": s.model_version,
            "symbols": s.symbols,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
        for s in strategies
    ]


@router.get("/active")
async def get_active_strategy(
    db: AsyncSession = Depends(get_db),
) -> Optional[dict]:
    """Get the currently active strategy for single user."""
    result = await db.execute(
        select(StrategyConfig).where(StrategyConfig.is_active == True)
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        return None
    return {
        "id": strategy.id,
        "name": strategy.name,
        "description": strategy.description,
        "version": strategy.version,
        "parameters": strategy.parameters,
        "model_version": strategy.model_version,
        "symbols": strategy.symbols,
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_strategy(
    name: str,
    description: Optional[str] = None,
    parameters: dict = {},
    symbols: list[str] = [],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new strategy configuration for single user."""
    strategy = StrategyConfig(
        name=name,
        description=description,
        parameters=parameters,
        symbols=symbols,
    )
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)
    return {
        "id": strategy.id,
        "name": strategy.name,
        "message": "Strategy created successfully",
    }


@router.post("/{strategy_id}/activate")
async def activate_strategy(
    strategy_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Activate a strategy for single user."""
    # Deactivate all other strategies
    await db.execute(
        select(StrategyConfig).where(StrategyConfig.is_active == True)
    )
    result = await db.execute(
        select(StrategyConfig).where(StrategyConfig.id == strategy_id)
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )
    strategy.is_active = True
    await db.commit()
    return {"message": f"Strategy '{strategy.name}' activated"}


# Example endpoint to use Claude reasoning layer for trade decision
@router.post("/claude_decide")
def claude_decide(features: dict, technical_signals: dict):
    ml_model = MLModel()
    signal_scorer = SignalScorer()
    claude = ClaudeReasoner()
    claude_service = ClaudeDecisionService(ml_model, signal_scorer, claude)
    result = claude_service.decide_trade(features, technical_signals)
    return result
