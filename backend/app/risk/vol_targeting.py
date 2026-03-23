"""Volatility targeting and forward vol forecasting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import structlog

from app.ml.base import safe_import

log = structlog.get_logger()
arch_pkg = safe_import("arch", "arch")


@dataclass
class VolTargetConfig:
    target_vol: float = 0.10  # annualized
    correlation_floor: float = 0.3
    max_leverage: float = 2.0


class VolTargeting:
    """Compute position sizes for constant target volatility."""

    def __init__(self, config: VolTargetConfig | None = None) -> None:
        self.config = config or VolTargetConfig()

    def forecast_vol(self, returns: np.ndarray) -> Optional[float]:
        if returns.size < 30:
            return float(np.std(returns) * np.sqrt(252))
        if not arch_pkg:
            log.warning("arch_missing", action="fallback_hist_vol")
            return float(np.std(returns[-252:]) * np.sqrt(252))
        try:
            am = arch_pkg.arch_model(returns * 100, vol="Garch", p=1, q=1, dist="normal")  # type: ignore[attr-defined]
            res = am.fit(disp="off")
            forecast = res.forecast(horizon=1).variance.iloc[-1, 0] / (100**2)
            return float(np.sqrt(forecast * 252))
        except Exception as exc:  # noqa: BLE001
            log.warning("garch_failed", error=str(exc))
            return float(np.std(returns[-252:]) * np.sqrt(252))

    def size(self, capital: float, asset_vol: float, corr_factor: float = 1.0) -> float:
        corr_adj = max(self.config.correlation_floor, corr_factor)
        position = (self.config.target_vol * capital) / max(asset_vol * corr_adj, 1e-6)
        capped = min(position, capital * self.config.max_leverage)
        return float(capped)

    def size_from_series(self, capital: float, returns: np.ndarray, corr_factor: float = 1.0) -> Dict[str, float]:
        fwd_vol = self.forecast_vol(returns)
        if not fwd_vol:
            return {"size": 0.0, "vol": None}
        return {"size": self.size(capital, fwd_vol, corr_factor), "vol": fwd_vol}
