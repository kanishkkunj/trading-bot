"""Backtest service."""

from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import OrderSide, OrderStatus
from app.schemas.market import HistoricalDataRequest
from app.services.market_service import MarketService
from app.services.memory_service import MemoryService


class BacktestResult:
    """Backtest result container."""

    def __init__(self):
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.metrics: dict = {}
        self.start_date: Optional[datetime] = None
        self.end_date: Optional[datetime] = None


class BacktestService:
    """Service for backtesting strategies."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.market_service = MarketService(db)
        self.memory_service = MemoryService()

    async def run_backtest(
        self,
        symbol: str,
        strategy_params: dict,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 100000.0,
        position_size_pct: float = 10.0,
    ) -> BacktestResult:
        """Run a backtest for a strategy."""
        result = BacktestResult()
        result.start_date = start_date
        result.end_date = end_date

        # Get historical data
        request = HistoricalDataRequest(
            symbol=symbol,
            timeframe="1d",
            from_date=start_date,
            to_date=end_date,
        )
        candles = await self.market_service.get_historical_data(request)

        if len(candles) < 50:
            raise ValueError("Insufficient historical data for backtest")

        # Convert to DataFrame
        df = pd.DataFrame([
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ])

        # Calculate indicators (simple SMA strategy for now)
        df["sma20"] = df["close"].rolling(window=20).mean()
        df["sma50"] = df["close"].rolling(window=50).mean()
        df["rsi"] = self._calculate_rsi(df["close"], 14)
        df["vwap"] = self._calculate_vwap(df)
        df["support20"] = df["low"].rolling(window=20).min()
        df["resistance20"] = df["high"].rolling(window=20).max()
        bb_mid = df["close"].rolling(window=20).mean()
        bb_std = df["close"].rolling(window=20).std()
        df["bb_upper"] = bb_mid + (2.0 * bb_std)
        df["bb_lower"] = bb_mid - (2.0 * bb_std)
        df["bb_z"] = (df["close"] - bb_mid) / (2.0 * bb_std).replace(0, np.nan)

        strategy_mode = str(strategy_params.get("strategy_mode", "hybrid")).lower()

        # Run simulation
        capital = initial_capital
        position = 0
        entry_price = 0.0
        equity = capital

        for i in range(50, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i - 1]

            # Generate signal
            signal = self._generate_signal(row, prev_row, strategy_mode)

            # Execute trades
            if signal == "BUY" and position == 0:
                position_size = (capital * position_size_pct / 100) / row["close"]
                position = int(position_size)
                entry_price = row["close"]
                capital -= position * entry_price

                result.trades.append({
                    "timestamp": row["timestamp"],
                    "action": "BUY",
                    "price": entry_price,
                    "quantity": position,
                    "capital": capital,
                })

            elif signal == "SELL" and position > 0:
                exit_price = row["close"]
                pnl = (exit_price - entry_price) * position
                capital += position * exit_price

                result.trades.append({
                    "timestamp": row["timestamp"],
                    "action": "SELL",
                    "price": exit_price,
                    "quantity": position,
                    "pnl": pnl,
                    "capital": capital,
                })

                position = 0
                entry_price = 0.0

            # Update equity
            equity = capital + (position * row["close"] if position > 0 else 0)
            result.equity_curve.append({
                "timestamp": row["timestamp"],
                "equity": equity,
                "position": position,
            })

        # Calculate metrics
        result.metrics = self._calculate_metrics(
            result.trades, result.equity_curve, initial_capital
        )

        # Persist summary to memory graph for future retrieval/analysis.
        await self.memory_service.log_backtest_summary(
            symbol=symbol,
            strategy_params=strategy_params,
            metrics=result.metrics,
            trades=result.trades,
        )

        return result

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Approximate rolling VWAP from OHLCV bars."""
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        return (typical * df["volume"]).cumsum() / df["volume"].replace(0, np.nan).cumsum()

    def _generate_signal(self, row: pd.Series, prev_row: pd.Series, strategy_mode: str = "hybrid") -> str:
        """Generate trading signal based on selected strategy mode.

        Modes:
        - trend_following: moving-average crossover + breakout confirmation
        - mean_reversion: RSI/Bollinger/VWAP reversion setup
        - hybrid: trend-following entries with mean-reversion exits
        """
        trend_buy = (
            prev_row["sma20"] <= prev_row["sma50"]
            and row["sma20"] > row["sma50"]
            and row["close"] > row["resistance20"] * 0.995
            and row["rsi"] < 75
        )
        trend_sell = (
            prev_row["sma20"] >= prev_row["sma50"]
            and row["sma20"] < row["sma50"]
            and row["close"] < row["support20"] * 1.005
            and row["rsi"] > 25
        )

        mr_buy = (
            row["rsi"] < 35
            and row["bb_z"] < -0.8
            and row["close"] < row["vwap"]
            and row["close"] <= row["support20"] * 1.01
        )
        mr_sell = (
            row["rsi"] > 65
            and row["bb_z"] > 0.8
            and row["close"] > row["vwap"]
            and row["close"] >= row["resistance20"] * 0.99
        )

        if strategy_mode == "trend_following":
            if trend_buy:
                return "BUY"
            if trend_sell:
                return "SELL"
            return "HOLD"

        if strategy_mode == "mean_reversion":
            if mr_buy:
                return "BUY"
            if mr_sell:
                return "SELL"
            return "HOLD"

        # hybrid
        if trend_buy or mr_buy:
            return "BUY"
        if trend_sell or mr_sell:
            return "SELL"
        return "HOLD"

    def _calculate_metrics(
        self,
        trades: list[dict],
        equity_curve: list[dict],
        initial_capital: float,
    ) -> dict:
        """Calculate backtest metrics."""
        if not trades or not equity_curve:
            return {}

        equity_values = [e["equity"] for e in equity_curve]
        returns = pd.Series(equity_values).pct_change().dropna()

        # Basic metrics
        final_equity = equity_values[-1]
        total_return = (final_equity - initial_capital) / initial_capital * 100

        # Win rate
        winning_trades = [t for t in trades if t.get("pnl", 0) > 0]
        win_rate = len(winning_trades) / len([t for t in trades if t["action"] == "SELL"]) * 100 if trades else 0

        # Drawdown
        peak = np.maximum.accumulate(equity_values)
        drawdown = (peak - equity_values) / peak
        max_drawdown = drawdown.max() * 100

        # Sharpe ratio (annualized, assuming 252 trading days)
        if len(returns) > 1 and returns.std() > 0:
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252)
        else:
            sharpe_ratio = 0

        # Profit factor
        gross_profit = sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) > 0)
        gross_loss = abs(sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        return {
            "initial_capital": round(initial_capital, 2),
            "final_equity": round(final_equity, 2),
            "total_return_pct": round(total_return, 2),
            "total_trades": len([t for t in trades if t["action"] == "SELL"]),
            "winning_trades": len(winning_trades),
            "losing_trades": len([t for t in trades if t.get("pnl", 0) < 0]),
            "win_rate_pct": round(win_rate, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "profit_factor": round(profit_factor, 2),
        }
