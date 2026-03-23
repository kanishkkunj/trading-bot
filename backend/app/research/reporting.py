"""Tear sheet style reporting (quantstats-like)."""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

try:  # optional dependency
    import quantstats as qs
except Exception:  # pragma: no cover
    qs = None  # type: ignore


class TearsheetReporter:
    """Generate performance tear sheets to HTML or CSV summaries."""

    def __init__(self) -> None:
        pass

    def to_tearsheet(self, returns: pd.Series, benchmark: Optional[pd.Series] = None, output: str = "report.html") -> None:
        if qs:
            qs.reports.html(returns, benchmark=benchmark, output=output, title="Tradecraft Strategy Report")
        else:
            summary = self.summary(returns, benchmark)
            with open(output, "w", encoding="utf-8") as f:
                f.write(summary.to_csv())

    def summary(self, returns: pd.Series, benchmark: Optional[pd.Series] = None) -> pd.DataFrame:
        df = pd.DataFrame({"returns": returns})
        if benchmark is not None:
            df["benchmark"] = benchmark.reindex_like(returns)
        df["cum_returns"] = (1 + df["returns"]).cumprod() - 1
        stats = {
            "cagr": (1 + df["returns"]).prod() ** (252 / max(len(df), 1)) - 1,
            "vol": df["returns"].std() * (252 ** 0.5),
            "sharpe": df["returns"].mean() / (df["returns"].std() + 1e-9) * (252 ** 0.5),
            "max_dd": ((df["cum_returns"] - df["cum_returns"].cummax()) / (df["cum_returns"].cummax() + 1e-9)).min(),
        }
        return pd.DataFrame(stats, index=["metrics"])
