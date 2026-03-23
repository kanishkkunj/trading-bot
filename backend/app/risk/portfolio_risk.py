"""Portfolio risk metrics: VaR, CVaR, stress, factor exposure, tracking error."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import structlog

log = structlog.get_logger()


@dataclass
class VarResult:
    var: float
    cvar: float
    method: str


class PortfolioRisk:
    """Risk analytics for portfolios."""

    def __init__(self, confidence: float = 0.95, mc_paths: int = 5000) -> None:
        self.confidence = confidence
        self.mc_paths = mc_paths

    def historical_var(self, pnl: np.ndarray) -> VarResult:
        if pnl.size == 0:
            return VarResult(var=0.0, cvar=0.0, method="historical")
        var = -np.percentile(pnl, (1 - self.confidence) * 100)
        tail = pnl[pnl <= np.percentile(pnl, (1 - self.confidence) * 100)]
        cvar = -tail.mean() if tail.size else var
        return VarResult(var=float(var), cvar=float(cvar), method="historical")

    def parametric_var(self, pnl: np.ndarray) -> VarResult:
        if pnl.size == 0:
            return VarResult(var=0.0, cvar=0.0, method="parametric")
        mu, sigma = pnl.mean(), pnl.std()
        z = 1.65 if self.confidence == 0.95 else 2.33
        var = -(mu - z * sigma)
        cvar = -(mu - sigma * (np.exp(-0.5 * z**2) / ((1 - self.confidence) * np.sqrt(2 * np.pi))))
        return VarResult(var=float(var), cvar=float(cvar), method="parametric")

    def monte_carlo_var(self, mu: float, sigma: float) -> VarResult:
        sims = np.random.normal(mu, sigma, size=self.mc_paths)
        return self.historical_var(sims)

    def stress_scenarios(self, returns: np.ndarray, shocks: Dict[str, float]) -> Dict[str, float]:
        results = {}
        for name, shock in shocks.items():
            shocked = returns + shock
            results[name] = float(np.mean(shocked))
        return results

    def factor_exposures(self, returns: np.ndarray, factors: np.ndarray) -> Optional[np.ndarray]:
        if returns.size == 0 or factors.size == 0:
            return None
        try:
            X = np.column_stack([np.ones(len(factors)), factors])
            beta, *_ = np.linalg.lstsq(X, returns, rcond=None)
            return beta
        except Exception as exc:  # noqa: BLE001
            log.warning("factor_regression_failed", error=str(exc))
            return None

    def tracking_error(self, portfolio_returns: np.ndarray, benchmark_returns: np.ndarray) -> Optional[float]:
        if portfolio_returns.size == 0 or benchmark_returns.size == 0:
            return None
        active = portfolio_returns - benchmark_returns
        return float(np.std(active) * np.sqrt(252))

    def run_stress_pack(self, returns: np.ndarray) -> Dict[str, float]:
        shocks = {
            "2008": -0.08,
            "covid": -0.06,
            "india_demonetization": -0.04,
        }
        return self.stress_scenarios(returns, shocks)

    def check_concentration(
        self,
        position_weights: Dict[str, float],
        max_single_weight: float = 0.20,
        max_sector_weight: float = 0.40,
        sector_map: Optional[Dict[str, str]] = None,
    ) -> "ConcentrationResult":
        """Return a ConcentrationResult flagging any position or sector limit breach.

        Args:
            position_weights:  {symbol: weight_as_fraction_of_portfolio}
            max_single_weight: Hard cap per single position (default 20%)
            max_sector_weight: Hard cap per sector bucket (default 40%)
            sector_map:        Optional {symbol: sector} mapping for grouping
        """
        breaches: List[str] = []

        for sym, w in position_weights.items():
            if w > max_single_weight:
                breaches.append(f"{sym} weight {w:.1%} > single limit {max_single_weight:.1%}")

        if sector_map:
            sector_totals: Dict[str, float] = {}
            for sym, w in position_weights.items():
                sector = sector_map.get(sym, "unknown")
                sector_totals[sector] = sector_totals.get(sector, 0.0) + w
            for sector, total in sector_totals.items():
                if total > max_sector_weight:
                    breaches.append(f"sector '{sector}' weight {total:.1%} > limit {max_sector_weight:.1%}")

        if breaches:
            log.warning("portfolio_concentration_breach", breaches=breaches)
            return ConcentrationResult(allowed=False, breaches=breaches)
        return ConcentrationResult(allowed=True, breaches=[])


@dataclass
class ConcentrationResult:
    allowed: bool
    breaches: List[str]
