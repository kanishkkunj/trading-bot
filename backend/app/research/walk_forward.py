"""Walk-forward analysis with regime stratification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

import numpy as np
import pandas as pd

from app.research.overfitting import deflated_sharpe_ratio


@dataclass
class WalkForwardResult:
    windows: List[Tuple[pd.Timestamp, pd.Timestamp]]
    metrics: List[Dict[str, float]]
    regime_metrics: Dict[str, Dict[str, float]]


class WalkForwardAnalyzer:
    """Automated train/test splits with rolling windows and regime metrics."""

    def __init__(self, lookback: int = 252, test_size: int = 63) -> None:
        self.lookback = lookback
        self.test_size = test_size

    def run(
        self,
        data: pd.DataFrame,
        target_col: str,
        regime_col: str,
        trainer: Callable[[pd.DataFrame, pd.Series], Callable[[pd.DataFrame], np.ndarray]],
    ) -> WalkForwardResult:
        windows: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
        metrics: List[Dict[str, float]] = []
        regime_metrics: Dict[str, Dict[str, float]] = {}

        for start in range(0, len(data) - self.lookback - self.test_size + 1, self.test_size):
            train = data.iloc[start : start + self.lookback]
            test = data.iloc[start + self.lookback : start + self.lookback + self.test_size]
            windows.append((test.index[0], test.index[-1]))

            model = trainer(train.drop(columns=[target_col]), train[target_col])
            preds = model(test.drop(columns=[target_col]))
            pnl = (preds * test[target_col]).sum()
            ret = preds * test[target_col]
            sharpe = ret.mean() / (ret.std() + 1e-9) * np.sqrt(252)
            dsr = deflated_sharpe_ratio(sharpe, len(ret))
            metrics.append({"pnl": float(pnl), "sharpe": float(sharpe), "deflated_sharpe": float(dsr)})

            for regime, grp in test.groupby(regime_col):
                if len(grp) == 0:
                    continue
                r_ret = (preds[test[regime_col] == regime] * grp[target_col])
                r_sharpe = r_ret.mean() / (r_ret.std() + 1e-9) * np.sqrt(252)
                r_dsr = deflated_sharpe_ratio(r_sharpe, len(r_ret))
                regime_metrics.setdefault(regime, {"pnl": 0.0, "count": 0, "sharpe_sum": 0.0, "dsr_sum": 0.0})
                regime_metrics[regime]["pnl"] += float(r_ret.sum())
                regime_metrics[regime]["count"] += 1
                regime_metrics[regime]["sharpe_sum"] += float(r_sharpe)
                regime_metrics[regime]["dsr_sum"] += float(r_dsr)

        # Average regime metrics
        for regime, vals in regime_metrics.items():
            cnt = max(vals["count"], 1)
            vals["sharpe_avg"] = vals["sharpe_sum"] / cnt
            vals["dsr_avg"] = vals["dsr_sum"] / cnt
        return WalkForwardResult(windows=windows, metrics=metrics, regime_metrics=regime_metrics)
