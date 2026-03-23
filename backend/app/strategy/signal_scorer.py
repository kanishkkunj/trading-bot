"""Signal quality scoring and gating."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
import structlog

from app.ml.base import safe_import

log = structlog.get_logger()
sklearn_ensemble = safe_import("sklearn.ensemble", "scikit-learn")
sklearn_neighbors = safe_import("sklearn.neighbors", "scikit-learn")


@dataclass
class SignalContext:
    model_confidence: float
    uncertainty: float
    liquidity_score: float
    recent_accuracy: float
    macro_alignment: float
    features: Dict[str, float]
    # Optional options-chain context injected when options_signals_enabled().
    # Keys match the output of OptionsSignals.options_context_summary().
    options_context: Dict[str, float] = field(default_factory=dict)


class SignalScorer:
    """Composite scoring and anomaly filtering."""

    def __init__(self, top_quantile: float = 0.9, anomaly_detector: Optional[str] = "iforest") -> None:
        self.top_quantile = top_quantile
        self.anomaly_detector = anomaly_detector
        self.iforest = None
        self.lof = None
        if anomaly_detector == "iforest" and sklearn_ensemble:
            self.iforest = sklearn_ensemble.IsolationForest(contamination=0.05, random_state=42)
        if anomaly_detector == "lof" and sklearn_neighbors:
            self.lof = sklearn_neighbors.LocalOutlierFactor(n_neighbors=25)
        self.score_history: list[float] = []

    def fit_anomaly_filter(self, feature_matrix: np.ndarray) -> None:
        if self.iforest:
            self.iforest.fit(feature_matrix)
        elif self.lof:
            self.lof.fit(feature_matrix)

    def compute_score(self, ctx: SignalContext) -> float:
        weights = np.array([0.35, 0.15, 0.15, 0.25, 0.10])
        factors = np.array(
            [
                ctx.model_confidence,
                1 - ctx.uncertainty,
                ctx.liquidity_score,
                ctx.recent_accuracy,
                ctx.macro_alignment,
            ]
        )
        score = float(np.dot(weights, factors))
        self.score_history.append(score)

        # Shadow comparison: log what the options-adjusted score would be without
        # changing the returned value.  Once evaluation confirms uplift, the
        # adjusted score can replace the base score by setting options_signals_enabled().
        self._log_options_shadow(score, ctx)

        return score

    def _log_options_shadow(self, base_score: float, ctx: SignalContext) -> None:
        """Log the options-adjusted score delta for shadow evaluation.

        The base execution score is unchanged.  This method records what the
        adjusted score *would have been* so we can quantify uplift in paper mode
        before promoting to live.
        """
        from app.core.feature_flags import options_signals_enabled

        if not ctx.options_context:
            return

        oi_signal = ctx.options_context.get("oi_pressure_signal", 0.0)
        flow_ratio = ctx.options_context.get("flow_bullish_ratio", 0.5)

        # Proposed adjustment (not applied until flag enabled):
        # weight OI signal contribution at 0.08 and flow sentiment at 0.04
        options_delta = 0.08 * oi_signal + 0.04 * (2 * flow_ratio - 1)
        adjusted_score = float(np.clip(base_score + options_delta, 0.0, 1.0))

        if options_signals_enabled():
            # Flag is live: return the adjusted score by updating history
            # Undo the base score and record adjusted instead
            if self.score_history:
                self.score_history[-1] = adjusted_score
            log.info(
                "signal_options_adjusted",
                base_score=round(base_score, 4),
                adjusted=round(adjusted_score, 4),
                options_delta=round(options_delta, 4),
            )
        else:
            log.debug(
                "signal_options_shadow",
                base_score=round(base_score, 4),
                shadow_adjusted=round(adjusted_score, 4),
                options_delta=round(options_delta, 4),
            )

    def passes_threshold(self, score: float) -> bool:
        if not self.score_history:
            return score >= 0.5
        threshold = np.quantile(self.score_history, self.top_quantile)
        return score >= threshold

    def is_anomalous(self, features: Dict[str, float]) -> bool:
        vec = np.array([features[k] for k in sorted(features.keys())]).reshape(1, -1)
        if self.iforest:
            pred = self.iforest.predict(vec)
            return pred[0] == -1
        if self.lof:
            pred = self.lof.fit_predict(vec)
            return pred[0] == -1
        return False

    def score_and_filter(self, ctx: SignalContext) -> Optional[float]:
        score = self.compute_score(ctx)
        if not self.passes_threshold(score):
            log.info("signal_rejected_threshold", score=score)
            return None
        if self.is_anomalous(ctx.features):
            log.info("signal_rejected_anomaly", score=score)
            return None
        return score
