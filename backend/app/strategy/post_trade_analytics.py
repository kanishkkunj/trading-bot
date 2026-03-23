"""Post-trade analytics and feedback loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import structlog

log = structlog.get_logger()


@dataclass
class TradeAttribution:
    alpha: float
    beta: float
    sector: float
    residual: float


class PostTradeAnalytics:
    """Attribution, execution review, and signal feedback."""

    def attribution(self, returns: np.ndarray, benchmark: np.ndarray, sector: np.ndarray) -> TradeAttribution:
        if returns.size == 0:
            return TradeAttribution(0.0, 0.0, 0.0, 0.0)
        X = np.column_stack([np.ones(len(benchmark)), benchmark, sector])
        beta, *_ = np.linalg.lstsq(X, returns, rcond=None)
        alpha = beta[0]
        beta_mkt = beta[1]
        beta_sector = beta[2]
        residual = returns - X @ beta
        return TradeAttribution(alpha=float(alpha), beta=float(beta_mkt), sector=float(beta_sector), residual=float(residual.mean()))

    def execution_review(self, arrival_price: float, fills: List[Dict[str, float]]) -> Dict[str, float]:
        if not fills:
            return {"slippage_bps": None, "fill_rate": 0.0}
        qty_total = sum(f.get("qty", 0.0) for f in fills)
        if qty_total == 0:
            return {"slippage_bps": None, "fill_rate": 0.0}
        vwap = sum(f.get("price", 0.0) * f.get("qty", 0.0) for f in fills) / qty_total
        side = 1 if fills[0].get("side", "BUY").upper() == "BUY" else -1
        slippage = (vwap - arrival_price) * side / arrival_price * 10000
        return {"slippage_bps": float(slippage), "fill_rate": float(qty_total)}

    def signal_performance(self, signals: List[Dict[str, float]]) -> Dict[str, float]:
        if not signals:
            return {}
        by_type: Dict[str, list[float]] = {}
        for s in signals:
            stype = s.get("type", "unknown")
            pnl = s.get("pnl", 0.0)
            by_type.setdefault(stype, []).append(pnl)
        return {k: float(np.mean(v)) for k, v in by_type.items()}

    def feedback(self, signal_metrics: Dict[str, float], trainer: Optional[any] = None) -> None:
        if trainer and hasattr(trainer, "log_feedback"):
            trainer.log_feedback(signal_metrics)
        log.info("signal_feedback", metrics=signal_metrics)
