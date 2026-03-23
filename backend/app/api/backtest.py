"""Backtest API routes."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.services.backtest_service import BacktestService

router = APIRouter()


@router.post("/run")
async def run_backtest(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    initial_capital: float = Query(default=100000.0, gt=0),
    position_size_pct: float = Query(default=10.0, gt=0, le=100),
    strategy_params: dict = {},
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run a backtest for a strategy (single user)."""
    backtest_service = BacktestService(db)
    try:
        result = await backtest_service.run_backtest(
            symbol=symbol,
            strategy_params=strategy_params,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            position_size_pct=position_size_pct,
        )
        return {
            "status": "success",
            "symbol": symbol,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "metrics": result.metrics,
            "trades_count": len(result.trades),
            "equity_curve_points": len(result.equity_curve),
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest failed: {str(e)}",
        )


@router.get("/quick/{symbol}")
async def quick_backtest(
    symbol: str,
    days: int = Query(default=365, ge=30, le=3650),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run a quick backtest with default parameters (single user)."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    backtest_service = BacktestService(db)
    try:
        result = await backtest_service.run_backtest(
            symbol=symbol,
            strategy_params={},
            start_date=start_date,
            end_date=end_date,
            initial_capital=100000.0,
            position_size_pct=10.0,
        )
        return {
            "status": "success",
            "symbol": symbol,
            "days": days,
            "metrics": result.metrics,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest failed: {str(e)}",
        )
