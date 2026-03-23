"""Paper trading orchestration endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.services.paper_trade_service import PaperTradeService

router = APIRouter()


@router.post("/run", status_code=status.HTTP_200_OK)
async def run_paper_trader(
    top_k: int = 5,
    db: AsyncSession = Depends(get_db),
):
    """Run ML ensemble paper trader and place orders for the single user."""
    if top_k <= 0:
        raise HTTPException(status_code=400, detail="top_k must be positive")
    service = PaperTradeService(db)
    user_id = 1  # Single-user mode
    try:
        executed = await service.run(user_id=user_id, top_k=top_k)
    except ValueError as exc:
        # Convert domain validation errors (e.g., notional caps) into 400 responses
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"executed": executed, "count": len(executed)}
