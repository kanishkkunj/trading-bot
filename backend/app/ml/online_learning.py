"""Adaptive online learning, drift detection, and A/B testing utilities."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import numpy as np
import structlog

from app.ml.base import PredictionResult, UncertaintyBreakdown, confidence_from_probs, safe_import

log = structlog.get_logger()

# Optional dependencies
river_drift = safe_import("river.drift", "river")
scipy_stats = safe_import("scipy.stats", "scipy")
torch = safe_import("torch", "torch")


@dataclass
class DriftSignal:
    """Represents a detected drift event."""

    kind: str
    p_value: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


class DriftDetector:
    """Detects concept/feature drift using ADWIN, Page-Hinkley, and KS tests."""

    def __init__(self, alpha: float = 0.05) -> None:
        self.alpha = alpha
        self.adwin = river_drift.ADWIN() if river_drift else None
        self.page_hinkley_mean = 0.0
        self.page_hinkley_min = 0.0
        self.page_hinkley_m = 0.0
        self.page_hinkley_lambda = 0.05
        self.page_hinkley_delta = 0.005
        self.feature_windows: Dict[str, Deque[float]] = {}
        self.window_size = 500

    def update_error(self, error: float) -> Optional[DriftSignal]:
        signal = None
        if self.adwin:
            self.adwin.update(error)
            if self.adwin.change_detected:  # pragma: no cover - depends on river runtime
                signal = DriftSignal(kind="adwin", details={"width": self.adwin.width})
        # Page-Hinkley
        self.page_hinkley_mean += (error - self.page_hinkley_mean) / (1 if self.page_hinkley_m == 0 else self.page_hinkley_m)
        self.page_hinkley_m += 1
        self.page_hinkley_min = min(self.page_hinkley_min, self.page_hinkley_mean)
        if self.page_hinkley_mean - self.page_hinkley_min > self.page_hinkley_lambda + self.page_hinkley_delta * self.page_hinkley_m:
            signal = DriftSignal(kind="page_hinkley", details={"mean": self.page_hinkley_mean})
            self._reset_page_hinkley()
        return signal

    def _reset_page_hinkley(self) -> None:
        self.page_hinkley_mean = 0.0
        self.page_hinkley_min = 0.0
        self.page_hinkley_m = 0.0

    def update_features(self, features: Dict[str, float]) -> List[DriftSignal]:
        signals: list[DriftSignal] = []
        if not scipy_stats:
            return signals
        for name, value in features.items():
            window = self.feature_windows.setdefault(name, deque(maxlen=self.window_size))
            window.append(value)
            if len(window) == window.maxlen:
                first_half = list(window)[: len(window) // 2]
                second_half = list(window)[len(window) // 2 :]
                stat, p_val = scipy_stats.ks_2samp(first_half, second_half)  # type: ignore[attr-defined]
                if p_val < self.alpha:
                    signals.append(DriftSignal(kind="ks_feature", p_value=float(p_val), details={"feature": name, "stat": float(stat)}))
        return signals


class FeatureImportanceStability:
    """Tracks stability of feature importance over time using cosine similarity."""

    def __init__(self, history: int = 20, threshold: float = 0.85) -> None:
        self.history = deque(maxlen=history)
        self.threshold = threshold

    def update(self, importances: Dict[str, float]) -> Optional[DriftSignal]:
        vector = np.array(list(importances.values()), dtype=float)
        if not self.history:
            self.history.append(vector)
            return None
        prev = self.history[-1]
        if vector.shape != prev.shape or np.linalg.norm(vector) == 0 or np.linalg.norm(prev) == 0:
            self.history.append(vector)
            return None
        cosine = float(np.dot(vector, prev) / (np.linalg.norm(vector) * np.linalg.norm(prev)))
        self.history.append(vector)
        if cosine < self.threshold:
            return DriftSignal(kind="feature_importance_shift", details={"cosine": cosine})
        return None


class ExperienceReplayBuffer:
    """Prioritized replay buffer for high-impact trades/events."""

    def __init__(self, capacity: int = 2000) -> None:
        self.capacity = capacity
        self.buffer: Deque[Tuple[np.ndarray, np.ndarray, float]] = deque(maxlen=capacity)

    def add(self, features: np.ndarray, label: np.ndarray, priority: float) -> None:
        self.buffer.append((features, label, priority))

    def sample(self, batch_size: int = 64) -> Tuple[np.ndarray, np.ndarray]:
        if not self.buffer:
            return np.array([]), np.array([])
        weights = np.array([abs(p) for *_, p in self.buffer], dtype=float)
        probs = weights / weights.sum()
        idx = np.random.choice(len(self.buffer), size=min(batch_size, len(self.buffer)), replace=False, p=probs)
        feats, labels = zip(*[(self.buffer[i][0], self.buffer[i][1]) for i in idx])
        return np.stack(feats), np.stack(labels)


class IncrementalXGBoost:
    """Handles incremental training for XGBoost using warm-started boosters."""

    def __init__(self, base_params: Optional[Dict[str, Any]] = None) -> None:
        xgb = safe_import("xgboost", "xgboost")
        if not xgb:
            raise ImportError("IncrementalXGBoost requires xgboost; install with pip install xgboost")
        self.xgb = xgb
        self.params = base_params or {"objective": "binary:logistic", "eval_metric": "logloss"}
        self.booster = None

    def fit(self, dtrain: Any, num_boost_round: int = 50, **kwargs: Any) -> None:
        self.booster = self.xgb.train(self.params, dtrain, num_boost_round=num_boost_round, **kwargs)

    def update(self, dtrain: Any, num_boost_round: int = 10, **kwargs: Any) -> None:
        if self.booster is None:
            self.fit(dtrain, num_boost_round=num_boost_round, **kwargs)
            return
        self.booster = self.xgb.train(
            self.params,
            dtrain,
            num_boost_round=num_boost_round,
            xgb_model=self.booster,
            **kwargs,
        )

    def predict_proba(self, dmatrix: Any) -> np.ndarray:
        if self.booster is None:
            raise RuntimeError("Booster not trained")
        preds = self.booster.predict(dmatrix)
        return np.column_stack([1 - preds, preds])


class NeuralOnlineLearner:
    """Continual learning loop for neural nets with experience replay."""

    def __init__(self, model: Any, buffer: ExperienceReplayBuffer, lr: float = 1e-4) -> None:
        if not torch:
            raise ImportError("NeuralOnlineLearner requires torch; install with pip install torch")
        self.model = model
        self.buffer = buffer
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.optim = torch.optim.Adam(self.model.parameters(), lr=lr)
        self.criterion = torch.nn.BCEWithLogitsLoss()

    def step(self, features: np.ndarray, labels: np.ndarray, replay: bool = True, replay_size: int = 64) -> float:
        self.model.train()
        x = torch.tensor(features, dtype=torch.float32).to(self.device)
        y = torch.tensor(labels, dtype=torch.float32).to(self.device)
        loss_val = self._train_batch(x, y)
        self.buffer.add(features, labels, priority=float(abs(labels.mean())))
        if replay:
            replay_feats, replay_labels = self.buffer.sample(replay_size)
            if replay_feats.size > 0:
                rx = torch.tensor(replay_feats, dtype=torch.float32).to(self.device)
                ry = torch.tensor(replay_labels, dtype=torch.float32).to(self.device)
                loss_val = 0.5 * loss_val + 0.5 * self._train_batch(rx, ry)
        return loss_val

    def _train_batch(self, x: Any, y: Any) -> float:
        self.optim.zero_grad()
        logits = self.model(x)
        logits = logits.squeeze() if logits.ndim > 1 else logits
        loss = self.criterion(logits, y)
        loss.backward()
        self.optim.step()
        return float(loss.item())


@dataclass
class BanditConfig:
    algorithm: str = "exp3"  # exp3 or thompson
    gamma: float = 0.1
    initial_weight: float = 1.0


class AdaptiveModelSelector:
    """Regime-aware model selection with explore-exploit bandits."""

    def __init__(self, config: BanditConfig | None = None) -> None:
        self.config = config or BanditConfig()
        self.models: dict[str, Any] = {}
        self.weights: dict[str, float] = {}
        self.rewards: dict[str, List[float]] = {}
        self.regime_models: dict[str, List[str]] = {}

    def register(self, name: str, model: Any, regime: Optional[str] = None) -> None:
        self.models[name] = model
        self.weights[name] = self.config.initial_weight
        self.rewards[name] = []
        if regime:
            self.regime_models.setdefault(regime, []).append(name)

    def choose(self, regime: Optional[str] = None) -> str:
        candidates = self.regime_models.get(regime, list(self.models.keys())) if regime else list(self.models.keys())
        if self.config.algorithm == "thompson":
            return self._thompson(candidates)
        return self._exp3(candidates)

    def _exp3(self, candidates: List[str]) -> str:
        weights = np.array([self.weights[c] for c in candidates], dtype=float)
        probs = (1 - self.config.gamma) * (weights / weights.sum()) + self.config.gamma / len(candidates)
        choice = np.random.choice(candidates, p=probs)
        return str(choice)

    def _thompson(self, candidates: List[str]) -> str:
        sampled = {c: np.random.beta(1 + sum(r), 1 + len(r) - sum(r)) if len(r) else np.random.random() for c, r in self.rewards.items() if c in candidates}
        return max(sampled, key=sampled.get)

    def update_reward(self, name: str, reward: float) -> None:
        self.rewards.setdefault(name, []).append(reward)
        if self.config.algorithm == "exp3":
            est_reward = reward / max(1e-6, self.weights.get(name, 1.0))
            self.weights[name] *= math.exp(self.config.gamma * est_reward / len(self.weights))
        self._normalize()

    def _normalize(self) -> None:
        total = sum(self.weights.values()) or 1.0
        for k in self.weights:
            self.weights[k] /= total


@dataclass
class PerformanceRecord:
    accuracy: float
    pnl: float
    latency_ms: float
    timestamp: Optional[str] = None


class FeedbackLoop:
    """Tracks model performance, supports human labeling, and causal impact estimation."""

    def __init__(self, label_handler: Optional[Callable[..., Any]] = None) -> None:
        self.metrics: dict[str, list[PerformanceRecord]] = {}
        self.label_handler = label_handler

    def record(self, model_name: str, record: PerformanceRecord) -> None:
        self.metrics.setdefault(model_name, []).append(record)

    def request_label(self, event: Dict[str, Any]) -> Any:
        if not self.label_handler:
            log.info("label_request_noop", event=event)
            return None
        return self.label_handler(event)

    def causal_impact(self, control: List[float], treated: List[float]) -> Dict[str, Any]:
        if not control or not treated:
            return {"uplift": None, "p_value": None}
        uplift = float(np.mean(treated) - np.mean(control))
        if scipy_stats:
            t_stat, p_val = scipy_stats.ttest_ind(treated, control, equal_var=False)  # type: ignore[attr-defined]
            return {"uplift": uplift, "p_value": float(p_val)}
        return {"uplift": uplift, "p_value": None}


class ABTester:
    """Simple A/B (canary/shadow) tester with significance checks."""

    def __init__(self, registry: Any, significance: float = 0.05) -> None:
        self.registry = registry
        self.significance = significance

    def route(self, versions: Dict[str, float]) -> Dict[str, float]:
        total = sum(versions.values()) or 1.0
        weights = {v: w / total for v, w in versions.items()}
        return self.registry.assign_canary(name="model", versions=weights) if hasattr(self.registry, "assign_canary") else weights

    def evaluate(self, control: List[float], treatment: List[float]) -> Dict[str, Any]:
        if scipy_stats and control and treatment:
            stat, p_val = scipy_stats.ttest_ind(treatment, control, equal_var=False)  # type: ignore[attr-defined]
            return {"p_value": float(p_val), "stat": float(stat), "significant": p_val < self.significance}
        return {"p_value": None, "stat": None, "significant": False}

    def promote(self, name: str, winner_version: str, loser_version: Optional[str] = None) -> None:
        if hasattr(self.registry, "promote"):
            self.registry.promote(name, winner_version, stage="Production")
        if loser_version and hasattr(self.registry, "rollback"):
            self.registry.rollback(name, loser_version)


class CogneeClient:
    """Thin wrapper to send decisions/outcomes to Cognee memory (optional)."""

    def __init__(self) -> None:
        self.client = safe_import("cognee", "cognee")

    def store(self, kind: str, payload: Dict[str, Any]) -> None:
        if not self.client:
            log.debug("cognee_missing", kind=kind)
            return
        try:  # pragma: no cover - external side effect
            self.client.save(kind=kind, data=payload)
        except Exception as exc:  # noqa: BLE001
            log.warning("cognee_store_failed", kind=kind, error=str(exc))


class OnlineLearningSystem:
    """Coordinates drift detection, online updates, model selection, and feedback."""

    def __init__(self, selector: AdaptiveModelSelector, feedback: FeedbackLoop, registry: Any, cognee: Optional[CogneeClient] = None) -> None:
        self.selector = selector
        self.feedback = feedback
        self.drift = DriftDetector()
        self.fi_tracker = FeatureImportanceStability()
        self.registry = registry
        self.cognee = cognee or CogneeClient()

    def process_prediction(
        self,
        X: np.ndarray,
        features: Dict[str, float],
        importances: Optional[Dict[str, float]] = None,
        regime: Optional[str] = None,
    ) -> Tuple[str, PredictionResult]:
        model_name = self.selector.choose(regime)
        model = self.selector.models[model_name]
        result: PredictionResult = model.predict_with_filters(X) if hasattr(model, "predict_with_filters") else PredictionResult(prediction=model.predict(X), probabilities=model.predict_proba(X))
        self._maybe_store_decision(model_name, result)
        if importances:
            shift = self.fi_tracker.update(importances)
            if shift:
                log.warning("feature_importance_shift", model=model_name, details=shift.details)
        drift_signals = self.drift.update_features(features)
        for sig in drift_signals:
            log.warning("feature_drift", feature=sig.details.get("feature"), stat=sig.details.get("stat"), p_value=sig.p_value)
        return model_name, result

    def record_outcome(self, model_name: str, y_true: np.ndarray, y_pred: np.ndarray, latency_ms: float, pnl: float) -> None:
        acc = float((y_true == y_pred).mean()) if len(y_true) else 0.0
        self.feedback.record(model_name, PerformanceRecord(accuracy=acc, pnl=pnl, latency_ms=latency_ms))
        reward = pnl
        self.selector.update_reward(model_name, reward=reward)
        error = float(np.mean(np.abs(y_true - y_pred))) if len(y_true) else 0.0
        drift = self.drift.update_error(error)
        if drift:
            log.warning("concept_drift_detected", model=model_name, kind=drift.kind, details=drift.details)
        self._maybe_store_outcome(model_name, acc, pnl, latency_ms)

    def _maybe_store_decision(self, model_name: str, result: PredictionResult) -> None:
        payload = {
            "model": model_name,
            "confidence": result.confidence,
            "uncertainty": result.uncertainty.__dict__ if result.uncertainty else None,
            "metadata": result.metadata,
        }
        self.cognee.store("decision", payload)

    def _maybe_store_outcome(self, model_name: str, accuracy: float, pnl: float, latency_ms: float) -> None:
        payload = {
            "model": model_name,
            "accuracy": accuracy,
            "pnl": pnl,
            "latency_ms": latency_ms,
        }
        self.cognee.store("outcome", payload)
