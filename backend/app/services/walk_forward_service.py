"""Walk-forward validation service.

Implements expanding-window walk-forward evaluation inspired by the fold-based
methodology from Repo 2 (sushant1827/Trading_Strategies), but built from
scratch to fit this architecture.  No code from that repository is reused.

Key design choices:
- Expanding train window (more historical data is always used as folds advance)
- Fixed test-window size (default: 20 trading-day equivalents per fold)
- Per-fold signal threshold search optimised on F1 is left for a future sprint;
  this version computes metrics at the `passes_threshold` level from SignalScorer
- Realistic cost assumption: slippage_bps + commission per trade is required
- Gate criteria: median fold net PnL > 0 AND worst-fold drawdown < 40%
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, TypedDict

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger()

# Default trading cost assumptions (in basis points and flat fee)
_DEFAULT_SLIPPAGE_BPS = 5   # 5 bps per side
_DEFAULT_COMMISSION = 20.0  # ₹20 per trade (approximate)

# Gate thresholds
_MIN_MEDIAN_NET_PNL = 0.0        # median fold net PnL must be positive
_MAX_WORST_FOLD_DRAWDOWN = 0.40  # worst-fold drawdown must be < 40%


class TradeRecord(TypedDict):
    pnl: float
    entry: float
    exit: float


@dataclass
class FoldResult:
    """Metrics for a single walk-forward fold."""

    fold_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    n_trades: int
    net_pnl: float
    net_pnl_pct: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    sharpe: float


def _fold_results_factory() -> list[FoldResult]:
    return []


@dataclass
class WalkForwardResult:
    """Aggregate walk-forward evaluation output."""

    symbol: str
    strategy_params: Dict[str, Any]
    n_folds: int
    folds: list[FoldResult] = field(default_factory=_fold_results_factory)

    # Aggregate stats across folds
    median_net_pnl: float = 0.0
    mean_net_pnl: float = 0.0
    worst_fold_drawdown_pct: float = 0.0
    best_fold_net_pnl: float = 0.0
    worst_fold_net_pnl: float = 0.0
    stddev_net_pnl: float = 0.0

    # Gate result
    gate_passed: bool = False
    gate_reason: str = ""

    def summary(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "n_folds": self.n_folds,
            "median_net_pnl": round(self.median_net_pnl, 2),
            "mean_net_pnl": round(self.mean_net_pnl, 2),
            "worst_fold_drawdown_pct": round(self.worst_fold_drawdown_pct, 2),
            "best_fold_net_pnl": round(self.best_fold_net_pnl, 2),
            "worst_fold_net_pnl": round(self.worst_fold_net_pnl, 2),
            "stddev_net_pnl": round(self.stddev_net_pnl, 2),
            "gate_passed": self.gate_passed,
            "gate_reason": self.gate_reason,
            "folds": [
                {
                    "fold": f.fold_index,
                    "net_pnl": round(f.net_pnl, 2),
                    "max_drawdown_pct": round(f.max_drawdown_pct, 2),
                    "win_rate": round(f.win_rate, 3),
                    "profit_factor": round(f.profit_factor, 3),
                    "n_trades": f.n_trades,
                }
                for f in self.folds
            ],
        }


class WalkForwardService:
    """Runs walk-forward evaluation on historical OHLCV data.

    Usage
    -----
    >>> svc = WalkForwardService()
    >>> df = ...  # pandas DataFrame with columns: open, high, low, close, volume
    >>> result = svc.evaluate(df, strategy_params={}, n_splits=5)
    >>> print(result.gate_passed, result.gate_reason)
    """

    def __init__(
        self,
        slippage_bps: float = _DEFAULT_SLIPPAGE_BPS,
        commission: float = _DEFAULT_COMMISSION,
    ) -> None:
        self.slippage_bps = slippage_bps
        self.commission = commission

    # ---------------------------------------------------------------------- public

    def evaluate(
        self,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        strategy_params: Optional[Dict[str, Any]] = None,
        n_splits: int = 5,
        min_train_bars: int = 50,
        test_size_bars: int = 20,
        initial_capital: float = 100_000.0,
        position_size_pct: float = 10.0,
    ) -> WalkForwardResult:
        """Run walk-forward evaluation with expanding training windows.

        Args:
            df:               Time-ordered OHLCV DataFrame (ascending by date).
            symbol:           Ticker label for reporting.
            strategy_params:  Passed through to signal generation.
            n_splits:         Number of folds.
            min_train_bars:   Minimum bars required in the training window.
            test_size_bars:   Bars in each test window.
            initial_capital:  Starting capital for each fold simulation.
            position_size_pct: Position size as % of capital per trade.

        Returns WalkForwardResult with per-fold metrics and gate evaluation.
        """
        params = strategy_params or {}
        result = WalkForwardResult(symbol=symbol, strategy_params=params, n_folds=n_splits)

        df = df.copy().reset_index(drop=True)
        total_bars = len(df)
        required = min_train_bars + n_splits * test_size_bars
        if total_bars < required:
            result.gate_reason = (
                f"Insufficient data: need {required} bars, have {total_bars}"
            )
            log.warning("walk_forward_insufficient_data", **{"required": required, "available": total_bars})
            return result

        for fold_idx in range(n_splits):
            train_end = min_train_bars + fold_idx * test_size_bars
            test_start = train_end
            test_end = test_start + test_size_bars

            if test_end > total_bars:
                break

            train_df = df.iloc[:train_end].copy()
            test_df = df.iloc[test_start:test_end].copy()

            fold = self._run_fold(
                fold_idx=fold_idx,
                train_df=train_df,
                test_df=test_df,
                strategy_mode=str(params.get("strategy_mode", "hybrid")),
                initial_capital=initial_capital,
                position_size_pct=position_size_pct,
                all_df=df,
            )
            result.folds.append(fold)

        self._compute_aggregate(result)
        self._evaluate_gate(result)
        log.info("walk_forward_complete", **result.summary())
        return result

    # ---------------------------------------------------------------------- private

    def _run_fold(
        self,
        fold_idx: int,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        strategy_mode: str,
        initial_capital: float,
        position_size_pct: float,
        all_df: pd.DataFrame,
    ) -> FoldResult:
        """Simulate the strategy on the test window using indicators from the full prefix."""
        # Compute indicators on the complete prefix (train + test) to avoid look-ahead
        prefix = all_df.iloc[: len(train_df) + len(test_df)].copy()
        prefix = self._compute_indicators(prefix)

        test_slice = prefix.iloc[len(train_df):]
        capital = initial_capital
        position = 0
        entry_price = 0.0
        trades: list[TradeRecord] = []
        equity_curve: list[float] = []

        for i in range(len(test_slice)):
            if i == 0:
                equity_curve.append(capital)
                continue

            row = test_slice.iloc[i]
            prev_row = test_slice.iloc[i - 1]

            signal = self._generate_signal(row, prev_row, strategy_mode)

            if signal == "BUY" and position == 0:
                raw_size = (capital * position_size_pct / 100) / float(row["close"])
                position = int(raw_size)
                if position <= 0:
                    equity_curve.append(capital)
                    continue
                entry_price = float(row["close"]) * (1 + self.slippage_bps / 10_000)
                capital -= position * entry_price + self.commission

            elif signal == "SELL" and position > 0:
                exit_price = float(row["close"]) * (1 - self.slippage_bps / 10_000)
                gross = position * exit_price - self.commission
                capital += gross
                pnl = gross - position * entry_price - self.commission
                trades.append({"pnl": pnl, "entry": entry_price, "exit": exit_price})
                position = 0
                entry_price = 0.0

            mark_to_market = capital + (position * float(row["close"]) if position > 0 else 0.0)
            equity_curve.append(mark_to_market)

        # Force-close any open position at last bar
        if position > 0 and len(test_slice) > 0:
            last_close = float(test_slice.iloc[-1]["close"]) * (1 - self.slippage_bps / 10_000)
            gross = position * last_close - self.commission
            capital += gross
            pnl = gross - position * entry_price - self.commission
            trades.append({"pnl": pnl, "entry": entry_price, "exit": last_close})
            equity_curve[-1] = capital

        net_pnl = capital - initial_capital
        return FoldResult(
            fold_index=fold_idx,
            train_start=datetime.now(),  # date columns optional in this harness
            train_end=datetime.now(),
            test_start=datetime.now(),
            test_end=datetime.now(),
            n_trades=len(trades),
            net_pnl=net_pnl,
            net_pnl_pct=net_pnl / initial_capital * 100,
            max_drawdown_pct=self._max_drawdown(equity_curve) * 100,
            win_rate=self._win_rate(trades),
            profit_factor=self._profit_factor(trades),
            sharpe=self._sharpe(equity_curve),
        )

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute the same indicator set used by BacktestService._generate_signal."""
        df = df.copy()
        df["sma20"] = df["close"].rolling(20).mean()
        df["sma50"] = df["close"].rolling(50).mean()
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-6)
        df["rsi"] = 100 - (100 / (1 + rs))
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        df["vwap"] = (typical * df["volume"]).cumsum() / df["volume"].replace(0, np.nan).cumsum()
        df["support20"] = df["low"].rolling(20).min()
        df["resistance20"] = df["high"].rolling(20).max()
        bb_mid = df["close"].rolling(20).mean()
        bb_std = df["close"].rolling(20).std()
        df["bb_upper"] = bb_mid + 2.0 * bb_std
        df["bb_lower"] = bb_mid - 2.0 * bb_std
        df["bb_z"] = (df["close"] - bb_mid) / (2.0 * bb_std + 1e-6)
        return df

    def _generate_signal(self, row: pd.Series, prev_row: pd.Series, strategy_mode: str) -> str:
        """Mirror of BacktestService._generate_signal to ensure consistency."""
        if any(
            pd.isna(row.get(col))
            for col in ("sma20", "sma50", "rsi", "vwap", "support20", "resistance20", "bb_z")
        ):
            return "HOLD"

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
            return "BUY" if trend_buy else ("SELL" if trend_sell else "HOLD")
        if strategy_mode == "mean_reversion":
            return "BUY" if mr_buy else ("SELL" if mr_sell else "HOLD")
        # hybrid
        return "BUY" if (trend_buy or mr_buy) else ("SELL" if (trend_sell or mr_sell) else "HOLD")

    # ---------------------------------------------------------------------- metrics

    @staticmethod
    def _max_drawdown(equity: list[float]) -> float:
        if not equity:
            return 0.0
        arr = np.array(equity, dtype=float)
        peak = np.maximum.accumulate(arr)
        dd = (peak - arr) / (peak + 1e-6)
        return float(dd.max())

    @staticmethod
    def _win_rate(trades: list[TradeRecord]) -> float:
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t["pnl"] > 0)
        return wins / len(trades)

    @staticmethod
    def _profit_factor(trades: list[TradeRecord]) -> float:
        gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
        if gross_loss < 1e-6:
            return math.inf if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    @staticmethod
    def _sharpe(equity: list[float], risk_free: float = 0.0) -> float:
        if len(equity) < 2:
            return 0.0
        rets = np.diff(equity) / (np.array(equity[:-1]) + 1e-6)
        excess = rets - risk_free / 252
        return float(excess.mean() / (excess.std() + 1e-6) * math.sqrt(252))

    def _compute_aggregate(self, result: WalkForwardResult) -> None:
        if not result.folds:
            return
        pnls = [f.net_pnl for f in result.folds]
        result.median_net_pnl = float(np.median(pnls))
        result.mean_net_pnl = float(np.mean(pnls))
        result.worst_fold_net_pnl = float(np.min(pnls))
        result.best_fold_net_pnl = float(np.max(pnls))
        result.stddev_net_pnl = float(np.std(pnls))
        result.worst_fold_drawdown_pct = float(max(f.max_drawdown_pct for f in result.folds))

    def _evaluate_gate(self, result: WalkForwardResult) -> None:
        """Check promotion gate criteria and set gate_passed + gate_reason."""
        from app.core.feature_flags import walk_forward_gate_enabled

        if not walk_forward_gate_enabled():
            result.gate_passed = True
            result.gate_reason = "walk_forward_gate disabled — promotion not blocked"
            return

        if not result.folds:
            result.gate_passed = False
            result.gate_reason = "No folds evaluated — insufficient data"
            return

        if result.median_net_pnl <= _MIN_MEDIAN_NET_PNL:
            result.gate_passed = False
            result.gate_reason = (
                f"Median fold net PnL {result.median_net_pnl:.2f} ≤ 0 — gate failed"
            )
            return

        if result.worst_fold_drawdown_pct >= _MAX_WORST_FOLD_DRAWDOWN * 100:
            result.gate_passed = False
            result.gate_reason = (
                f"Worst-fold drawdown {result.worst_fold_drawdown_pct:.1f}% ≥ "
                f"{_MAX_WORST_FOLD_DRAWDOWN * 100:.0f}% limit — gate failed"
            )
            return

        result.gate_passed = True
        result.gate_reason = (
            f"Gate passed: median PnL={result.median_net_pnl:.2f}, "
            f"worst drawdown={result.worst_fold_drawdown_pct:.1f}%"
        )
