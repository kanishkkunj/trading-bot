"""Performance dashboard metrics and attribution."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

import structlog

try:  # Optional Prometheus dependency
    from prometheus_client import Counter, Gauge, Histogram
except Exception:  # pragma: no cover
    class _NoOp:  # type: ignore
        def labels(self, *_, **__):
            return self

        def inc(self, *_args, **_kwargs):
            return None

        def set(self, *_args, **_kwargs):
            return None

        def observe(self, *_args, **_kwargs):
            return None

    def Counter(*_args, **_kwargs):
        return _NoOp()

    def Gauge(*_args, **_kwargs):
        return _NoOp()

    def Histogram(*_args, **_kwargs):
        return _NoOp()


log = structlog.get_logger()


@dataclass
class PerformanceSnapshot:
    timestamp: float
    equity: float
    pnl: float
    drawdown: float
    sharpe: float
    strategy_attrib: Dict[str, float]
    regime_accuracy: Dict[str, float]
    execution_slippage_bps: float


class PerformanceMonitor:
    """Tracks P&L, drawdowns, Sharpe, attribution, and execution quality."""

    def __init__(self, max_history: int = 500) -> None:
        self.equity_curve: Deque[float] = deque(maxlen=max_history)
        self.returns: Deque[float] = deque(maxlen=max_history)
        self.strategy_pnl: Dict[str, float] = defaultdict(float)
        self.regime_outcomes: Dict[str, Tuple[int, int]] = defaultdict(lambda: (0, 0))  # correct, total
        self.execution_slippage: Deque[float] = deque(maxlen=max_history)

        # Prometheus metrics
        self.pnl_gauge = Gauge("pnl_total", "Total PnL")
        self.sharpe_gauge = Gauge("sharpe_ratio", "Rolling Sharpe ratio")
        self.drawdown_gauge = Gauge("drawdown_pct", "Current drawdown percentage")
        self.strategy_pnl_gauge = Gauge("strategy_pnl", "PnL by strategy", ["strategy"])
        self.regime_accuracy_gauge = Gauge("regime_accuracy", "Model accuracy by regime", ["regime"])
        self.exec_slippage_hist = Histogram("execution_slippage_bps", "Execution slippage (bps)")

    def record_trade(self, strategy: str, pnl: float, equity: float) -> None:
        """Record realized P&L and update equity curve."""
        self.strategy_pnl[strategy] += pnl
        self.equity_curve.append(equity)
        if len(self.equity_curve) >= 2:
            ret = (self.equity_curve[-1] - self.equity_curve[-2]) / max(self.equity_curve[-2], 1e-9)
            self.returns.append(ret)
        self.pnl_gauge.set(sum(self.strategy_pnl.values()))
        self.strategy_pnl_gauge.labels(strategy=strategy).set(self.strategy_pnl[strategy])

    def record_execution(self, intended_price: float, filled_price: float) -> None:
        """Capture execution slippage in basis points."""
        if intended_price <= 0:
            return
        slippage_bps = ((filled_price - intended_price) / intended_price) * 10_000
        self.execution_slippage.append(slippage_bps)
        self.exec_slippage_hist.observe(slippage_bps)

    def record_model_outcome(self, regime: str, correct: bool) -> None:
        """Track model correctness per regime."""
        wins, total = self.regime_outcomes[regime]
        self.regime_outcomes[regime] = (wins + int(correct), total + 1)
        acc = (wins + int(correct)) / max(total + 1, 1)
        self.regime_accuracy_gauge.labels(regime=regime).set(acc)

    def metrics(self, now: float) -> PerformanceSnapshot:
        drawdown = self._drawdown_pct()
        sharpe = self._sharpe_ratio()
        regime_acc = {k: (v[0] / v[1]) if v[1] else 0.0 for k, v in self.regime_outcomes.items()}
        exec_slip = sum(self.execution_slippage) / len(self.execution_slippage) if self.execution_slippage else 0.0

        self.sharpe_gauge.set(sharpe)
        self.drawdown_gauge.set(drawdown)

        return PerformanceSnapshot(
            timestamp=now,
            equity=self.equity_curve[-1] if self.equity_curve else 0.0,
            pnl=sum(self.strategy_pnl.values()),
            drawdown=drawdown,
            sharpe=sharpe,
            strategy_attrib=dict(self.strategy_pnl),
            regime_accuracy=regime_acc,
            execution_slippage_bps=exec_slip,
        )

    def _drawdown_pct(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = -1e9
        dd = 0.0
        for val in self.equity_curve:
            peak = max(peak, val)
            if peak > 0:
                dd = min(dd, (val - peak) / peak)
        return abs(dd) * 100

    def _sharpe_ratio(self, risk_free: float = 0.0) -> float:
        if not self.returns:
            return 0.0
        mean_ret = sum(self.returns) / len(self.returns)
        var = sum((r - mean_ret) ** 2 for r in self.returns) / max(len(self.returns) - 1, 1)
        std = var ** 0.5
        if std == 0:
            return 0.0
        # Assume daily returns -> annualize by sqrt(252)
        return ((mean_ret - risk_free) / std) * 252 ** 0.5

    def reset(self) -> None:
        """Clear in-memory trackers."""
        self.equity_curve.clear()
        self.returns.clear()
        self.strategy_pnl.clear()
        self.regime_outcomes.clear()
        self.execution_slippage.clear()
