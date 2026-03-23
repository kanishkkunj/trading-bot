"""Portfolio API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.portfolio import (
    PositionResponse,
    PortfolioSummary,
    PnLResponse,
)
from app.services.portfolio_service import PortfolioService
from app.config import get_settings

router = APIRouter()


@router.get("/positions", response_model=list[PositionResponse])
async def get_positions(
    db: AsyncSession = Depends(get_db),
) -> list[PositionResponse]:
    """Get current positions for single user."""
    portfolio_service = PortfolioService(db)
    user_id = 1  # Single-user mode
    positions = await portfolio_service.get_positions(user_id, only_open=True)
    return [PositionResponse.model_validate(p) for p in positions]


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    db: AsyncSession = Depends(get_db),
) -> PortfolioSummary:
    """Get portfolio summary for single user."""
    portfolio_service = PortfolioService(db)
    user_id = 1  # Single-user mode
    summary = await portfolio_service.get_portfolio_summary(user_id)
    return PortfolioSummary(**summary)


@router.get("/pnl", response_model=PnLResponse)
async def get_pnl(
    db: AsyncSession = Depends(get_db),
) -> PnLResponse:
    """Get PnL information for single user."""
    portfolio_service = PortfolioService(db)
    user_id = 1  # Single-user mode
    daily_pnl = await portfolio_service.get_daily_pnl(user_id)
    summary = await portfolio_service.get_portfolio_summary(user_id)
    account = await portfolio_service.get_account_snapshot(user_id)
    settings = get_settings()
    initial_capital = float(getattr(settings, "PAPER_INITIAL_CAPITAL", 1_000_000.0) or 1_000_000.0)
    denom = initial_capital if initial_capital != 0 else 1.0
    return PnLResponse(
        initial_capital=initial_capital,
        cash=account["cash"],
        equity=account["equity"],
        long_exposure=account["long_cost"],
        short_proceeds=account["short_proceeds"],
        daily_pnl=daily_pnl["daily_total_pnl"],
        daily_realized_pnl=daily_pnl["daily_realized_pnl"],
        daily_unrealized_pnl=daily_pnl["daily_unrealized_pnl"],
        daily_pnl_pct=round((daily_pnl["daily_total_pnl"] / denom) * 100, 4),
        total_pnl=summary["total_pnl"],
        total_realized_pnl=summary["total_realized_pnl"],
        total_unrealized_pnl=summary["total_unrealized_pnl"],
        total_pnl_pct=round((summary["total_pnl"] / denom) * 100, 4),
        max_drawdown=0.0,  # TODO: Calculate from equity curve
        sharpe_ratio=None,  # TODO: Calculate from returns
    )
