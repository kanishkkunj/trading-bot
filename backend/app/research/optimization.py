"""Parameter optimization utilities using Optuna."""

from __future__ import annotations

from typing import Callable, Dict, Optional

try:
    import optuna
except Exception:  # pragma: no cover
    optuna = None  # type: ignore


class OptunaTuner:
    """Wrap Optuna for hyperparameter sweeps."""

    def __init__(self, study_name: str = "tradecraft-opt", storage: Optional[str] = None) -> None:
        self.study_name = study_name
        self.storage = storage
        if optuna:
            self.study = optuna.create_study(study_name=study_name, storage=storage, direction="maximize", load_if_exists=True)
        else:
            self.study = None

    def optimize(self, objective: Callable[["optuna.trial.Trial"], float], n_trials: int = 50) -> Dict[str, float]:
        if not optuna or self.study is None:
            return {}
        self.study.optimize(objective, n_trials=n_trials)
        return self.study.best_params if self.study.best_trial else {}
