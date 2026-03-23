"""Training pipeline with time-series CV, Optuna HPO, feature selection, and drift triggers."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import structlog
from sklearn.feature_selection import RFE
from sklearn.metrics import accuracy_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.ensemble import RandomForestClassifier

from app.ml.model_registry import ModelRegistry

log = structlog.get_logger()
try:  # pragma: no cover - optional dependency
    import optuna
except ImportError:  # pragma: no cover
    optuna = None

try:  # pragma: no cover - optional dependency
    from boruta import BorutaPy
except ImportError:  # pragma: no cover
    BorutaPy = None


@dataclass
class PipelineConfig:
    n_splits: int = 5
    embargo_days: int = 5
    optuna_trials: int = 25
    retrain_drop_threshold: float = 0.05
    drift_window: int = 30


class TrainingPipeline:
    """Full training orchestration with CV, HPO, feature selection, and drift triggers."""

    def __init__(self, config: PipelineConfig, registry: ModelRegistry | None = None) -> None:
        self.config = config
        self.registry = registry or ModelRegistry()

    def purged_splits(self, dates: pd.Series) -> Iterable[Tuple[np.ndarray, np.ndarray]]:
        tscv = TimeSeriesSplit(n_splits=self.config.n_splits)
        embargo = pd.Timedelta(days=self.config.embargo_days)
        for train_idx, test_idx in tscv.split(dates):
            train_end = dates.iloc[train_idx].max()
            embargo_mask = dates.iloc[test_idx] <= (train_end + embargo)
            filtered_test = np.array(test_idx)[~embargo_mask.to_numpy()]
            if filtered_test.size == 0:
                continue
            yield train_idx, filtered_test

    def feature_select(self, X: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
        if BorutaPy:
            selector = BorutaPy(RandomForestClassifier(n_estimators=200, n_jobs=-1), n_estimators="auto")
            selector.fit(X.values, y.values)
            mask = selector.support_ if hasattr(selector, "support_") else []
            cols = [c for c, keep in zip(X.columns, mask) if keep]
            if cols:
                log.info("boruta_selected", cols=len(cols))
                return X[cols]
        # Fallback to RFE
        estimator = RandomForestClassifier(n_estimators=200, n_jobs=-1)
        rfe = RFE(estimator, n_features_to_select=min(50, X.shape[1]))
        rfe.fit(X, y)
        cols = [c for c, keep in zip(X.columns, rfe.support_) if keep]
        log.info("rfe_selected", cols=len(cols))
        return X[cols]

    def hyperopt(self, objective: Callable[[dict[str, Any]], float], search_space: dict[str, Any]) -> dict[str, Any]:
        if not optuna:
            log.warning("optuna_missing", action="using_default_params")
            return {k: v[0] if isinstance(v, (list, tuple)) else v for k, v in search_space.items()}

        def objective_wrapper(trial: Any) -> float:
            params = {k: trial.suggest_float(k, v[0], v[1]) if isinstance(v, tuple) else trial.suggest_categorical(k, v) for k, v in search_space.items()}
            return objective(params)

        study = optuna.create_study(direction="maximize")
        study.optimize(objective_wrapper, n_trials=self.config.optuna_trials)
        log.info("optuna_best", params=study.best_params, value=study.best_value)
        return study.best_params

    def walk_forward(
        self,
        data: pd.DataFrame,
        feature_cols: Sequence[str],
        target_col: str,
        train_func: Callable[[pd.DataFrame, pd.DataFrame], Any],
        predict_func: Callable[[pd.DataFrame, Any], np.ndarray],
        window: int = 252,
        step: int = 21,
    ) -> List[float]:
        metrics: list[float] = []
        for start in range(0, len(data) - window, step):
            train_df = data.iloc[start : start + window]
            test_df = data.iloc[start + window : start + window + step]
            if test_df.empty:
                break
            model = train_func(train_df[feature_cols], train_df[target_col])
            preds = predict_func(test_df[feature_cols], model)
            acc = accuracy_score(test_df[target_col], preds)
            metrics.append(acc)
            log.debug("walk_forward_step", start=start, acc=round(acc, 4))
        return metrics

    def should_retrain(self, recent_scores: List[float]) -> bool:
        if len(recent_scores) < self.config.drift_window:
            return False
        recent = recent_scores[-self.config.drift_window :]
        if not recent:
            return False
        drop = np.mean(recent) - np.max(recent)
        return drop <= -self.config.retrain_drop_threshold

    def save_model(self, name: str, version: str, artifact_path: str, metrics: dict[str, Any]) -> None:
        self.registry.register(name=name, version=version, path=artifact_path, metrics=metrics)

    def log_experiment(self, name: str, params: dict[str, Any], metrics: dict[str, Any]) -> None:
        log.info("experiment", name=name, params=params, metrics=metrics)
