"""Market regime detection using HMM, GMM, and RF with transition alerts."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

from app.ml.base import safe_import
from app.models.regime import Regime, RegimeType

log = structlog.get_logger()

# Optional dependencies
hmmlearn = safe_import("hmmlearn.hmm", "hmmlearn")
sklearn_mixture = safe_import("sklearn.mixture", "scikit-learn")
sklearn_ensemble = safe_import("sklearn.ensemble", "scikit-learn")
sklearn_metrics = safe_import("sklearn.metrics", "scikit-learn")


VOL_BUCKETS = [15, 25, 40]
TREND_LABELS = ["strong_down", "weak_down", "sideways", "weak_up", "strong_up"]
CORR_LABELS = ["risk_off", "normal", "risk_on"]
LIQ_LABELS = ["crisis", "stressed", "normal"]


@dataclass
class RegimeProbabilities:
    """Probability scores for each detected regime dimension."""

    volatility: Dict[str, float] = field(default_factory=dict)
    trend: Dict[str, float] = field(default_factory=dict)
    correlation: Dict[str, float] = field(default_factory=dict)
    liquidity: Dict[str, float] = field(default_factory=dict)
    transition_5d: Optional[float] = None
    transition_10d: Optional[float] = None


@dataclass
class RegimeSnapshot:
    """Current regime snapshot and metadata."""

    timestamp: dt.datetime
    volatility: str
    trend: str
    correlation: str
    liquidity: str
    confidence: float
    probs: RegimeProbabilities
    features: Dict[str, float]
    early_warnings: List[str] = field(default_factory=list)


class RegimeDetector:
    """Detects market regimes and transition risks using multiple models."""

    def __init__(
        self,
        n_gmm: int = 4,
        hmm_states: int = 4,
        rf_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.gmm = sklearn_mixture.GaussianMixture(n_components=n_gmm) if sklearn_mixture else None
        self.hmm = hmmlearn.GaussianHMM(n_components=hmm_states) if hmmlearn else None
        rf_cls = sklearn_ensemble.RandomForestClassifier if sklearn_ensemble else None
        self.rf = rf_cls(**(rf_params or {})) if rf_cls else None
        self.history: list[RegimeSnapshot] = []

    # --- Regime classification helpers ---
    @staticmethod
    def bucket_vol(vol_pct: float) -> Tuple[str, float]:
        levels = ["low", "medium", "high", "extreme"]
        thresholds = VOL_BUCKETS + [float("inf")]
        for level, thr in zip(levels, thresholds):
            if vol_pct < thr:
                return level, 1.0
        return "extreme", 1.0

    @staticmethod
    def classify_trend(return_series: np.ndarray) -> Tuple[str, float]:
        if len(return_series) < 5:
            return "sideways", 0.3
        slope = np.polyfit(np.arange(len(return_series)), return_series, deg=1)[0]
        vol = np.std(return_series) + 1e-6
        t_stat = slope / vol
        if t_stat > 2.5:
            return "strong_up", 0.9
        if t_stat > 1.0:
            return "weak_up", 0.7
        if t_stat < -2.5:
            return "strong_down", 0.9
        if t_stat < -1.0:
            return "weak_down", 0.7
        return "sideways", 0.6

    @staticmethod
    def classify_correlation(mean_corr: float, spike_flag: bool = False) -> Tuple[str, float]:
        if spike_flag and mean_corr < 0.3:
            return "risk_off", 0.8
        if mean_corr > 0.65:
            return "risk_on", 0.7
        if mean_corr < 0.3:
            return "risk_off", 0.7
        return "normal", 0.6

    @staticmethod
    def classify_liquidity(spread_bps: float, depth_score: float) -> Tuple[str, float]:
        if spread_bps > 40 or depth_score < 0.2:
            return "crisis", 0.9
        if spread_bps > 20 or depth_score < 0.5:
            return "stressed", 0.7
        return "normal", 0.6

    # --- Model-based probabilities ---
    def _gmm_probs(self, X: np.ndarray) -> Dict[str, float]:
        if self.gmm is None:
            return {}
        try:
            comps = self.gmm.predict_proba(X[-1:])[0]
            return {f"gmm_{i}": float(p) for i, p in enumerate(comps)}
        except Exception as exc:  # noqa: BLE001
            log.warning("gmm_probs_failed", error=str(exc))
            return {}

    def _hmm_probs(self, X: np.ndarray) -> Dict[str, float]:
        if self.hmm is None:
            return {}
        try:
            post = self.hmm.predict_proba(X[-1:])[0]
            return {f"hmm_{i}": float(p) for i, p in enumerate(post)}
        except Exception as exc:  # noqa: BLE001
            log.warning("hmm_probs_failed", error=str(exc))
            return {}

    def _rf_probs(self, X: np.ndarray) -> Dict[str, float]:
        if self.rf is None:
            return {}
        try:
            probs = self.rf.predict_proba(X[-1:])[0]
            classes = getattr(self.rf, "classes_", np.arange(len(probs)))
            return {str(cls): float(p) for cls, p in zip(classes, probs)}
        except Exception as exc:  # noqa: BLE001
            log.warning("rf_probs_failed", error=str(exc))
            return {}

    # --- Main detection ---
    def detect(
        self,
        features: Dict[str, float],
        returns: np.ndarray,
        corr_mean: float,
        corr_spike: bool,
        spread_bps: float,
        depth_score: float,
        macro_flags: Optional[Dict[str, bool]] = None,
        horizon_days: Tuple[int, int] = (5, 10),
    ) -> RegimeSnapshot:
        vol = features.get("volatility_pct", 0.0)
        vol_regime, vol_conf = self.bucket_vol(vol)
        trend_regime, trend_conf = self.classify_trend(returns)
        corr_regime, corr_conf = self.classify_correlation(corr_mean, corr_spike)
        liq_regime, liq_conf = self.classify_liquidity(spread_bps, depth_score)

        # Model-based probabilities
        X = np.array([[features.get(k, 0.0) for k in sorted(features.keys())]])
        probs = RegimeProbabilities(
            volatility={vol_regime: vol_conf} | self._gmm_probs(X),
            trend={trend_regime: trend_conf},
            correlation={corr_regime: corr_conf} | self._hmm_probs(X),
            liquidity={liq_regime: liq_conf} | self._rf_probs(X),
        )

        transition_5, transition_10, warnings = self._transition_risk(vol, corr_mean, macro_flags, horizon_days)
        probs.transition_5d = transition_5
        probs.transition_10d = transition_10

        confidence = float(np.mean([vol_conf, trend_conf, corr_conf, liq_conf]))
        snapshot = RegimeSnapshot(
            timestamp=dt.datetime.utcnow(),
            volatility=vol_regime,
            trend=trend_regime,
            correlation=corr_regime,
            liquidity=liq_regime,
            confidence=confidence,
            probs=probs,
            features=features,
            early_warnings=warnings,
        )
        self.history.append(snapshot)
        return snapshot

    def _transition_risk(
        self, vol: float, corr_mean: float, macro_flags: Optional[Dict[str, bool]], horizon: Tuple[int, int]
    ) -> Tuple[float, float, List[str]]:
        warnings: list[str] = []
        spike_flag = corr_mean > 0.7
        vol_jump = vol > 25
        macro = macro_flags or {}
        prob5 = min(0.95, 0.1 + 0.02 * max(0, vol - 15) + (0.1 if spike_flag else 0))
        prob10 = min(0.95, prob5 + 0.05)
        if vol_jump:
            warnings.append("volatility_cluster")
        if spike_flag:
            warnings.append("correlation_spike")
        if any(macro.values()):
            warnings.append("macro_event_risk")
        return float(prob5), float(prob10), warnings

    # --- Regime-aware trading policies ---
    def strategy_overrides(self, snapshot: RegimeSnapshot) -> Dict[str, Any]:
        disables: list[str] = []
        sizing_factor = 1.0
        model_hints: list[str] = []
        if snapshot.trend in {"strong_up", "strong_down"}:
            disables.append("mean_reversion")
            model_hints.append("trend_following")
        if snapshot.volatility in {"high", "extreme"}:
            sizing_factor *= 0.6
            disables.append("short_vol")
        if snapshot.correlation == "risk_off":
            disables.append("high_beta")
        if snapshot.liquidity == "crisis":
            sizing_factor *= 0.5
            disables.append("illiquid_pairs")
        return {
            "disable": disables,
            "position_sizing_multiplier": sizing_factor,
            "preferred_models": model_hints,
        }

    # --- Persistence metrics ---
    def persistence_stats(self, lookback: int = 200) -> Dict[str, Any]:
        hist = self.history[-lookback:]
        if not hist:
            return {}
        durations: Dict[str, int] = {}
        last = None
        length = 0
        for snap in hist:
            if snap.volatility != last:
                if last is not None:
                    durations[last] = durations.get(last, 0) + length
                last = snap.volatility
                length = 1
            else:
                length += 1
        if last is not None:
            durations[last] = durations.get(last, 0) + length
        avg_length = {k: v / max(1, sum(hist[i].volatility == k for i in range(len(hist)))) for k, v in durations.items()}
        return {"durations": durations, "avg_length": avg_length}

    # --- Persistence to DB (optional) ---
    def persist(self, snapshot: RegimeSnapshot, session: Any) -> None:
        try:
            record = Regime(
                id=None,
                regime_type=RegimeType.BULL if snapshot.trend in {"strong_up", "weak_up"} else RegimeType.BEAR,
                label=f"vol={snapshot.volatility}|trend={snapshot.trend}|corr={snapshot.correlation}|liq={snapshot.liquidity}",
                confidence=snapshot.confidence,
                start_time=snapshot.timestamp,
                end_time=None,
                detector_version="regime-detector-v1",
                symbols=None,
                features_snapshot=snapshot.features,
                notes=",".join(snapshot.early_warnings),
                created_at=snapshot.timestamp,
            )
            session.add(record)
            session.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("regime_persist_failed", error=str(exc))
