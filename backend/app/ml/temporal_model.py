"""Temporal sequence model (LSTM/GRU with attention) with MC Dropout."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

import numpy as np
import structlog

from app.ml.base import BaseProbModel, PredictionResult, UncertaintyBreakdown, confidence_from_probs, entropy_from_probs, safe_import

log = structlog.get_logger()

torch = safe_import("torch", "torch")
if torch:
    nn = torch.nn
    optim = torch.optim
else:  # pragma: no cover - optional dependency guard
    nn = None
    optim = None


@dataclass
class TemporalConfig:
    """Config for temporal model."""

    model_type: str = "lstm"  # lstm or gru
    input_dim: int = 64
    hidden_dim: int = 128
    num_layers: int = 2
    dropout: float = 0.2
    bidirectional: bool = False


class _Attention(nn.Module if nn else object):  # type: ignore[misc]
    def __init__(self, hidden_dim: int) -> None:
        if not nn:  # pragma: no cover - optional dependency guard
            return
        super().__init__()
        self.linear = nn.Linear(hidden_dim, 1)

    def forward(self, x: Any) -> Tuple[Any, Any]:
        scores = self.linear(x).squeeze(-1)  # [batch, time]
        weights = torch.softmax(scores, dim=-1)
        context = (x * weights.unsqueeze(-1)).sum(dim=1)
        return context, weights


class TemporalModel(BaseProbModel):
    """Sequence model with attention and uncertainty via MC dropout."""

    def __init__(self, config: TemporalConfig) -> None:
        if not torch:
            raise ImportError("TemporalModel requires torch; install with pip install torch")
        self.config = config
        self.model = self._build_model()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)

    def _build_model(self) -> Any:
        input_dim = self.config.input_dim
        hidden = self.config.hidden_dim
        layers = self.config.num_layers
        bidir = self.config.bidirectional
        model_type = self.config.model_type.lower()
        dropout = self.config.dropout

        class Net(nn.Module):  # type: ignore[misc]
            def __init__(self) -> None:
                super().__init__()
                rnn_cls = nn.GRU if model_type == "gru" else nn.LSTM
                self.rnn = rnn_cls(
                    input_size=input_dim,
                    hidden_size=hidden,
                    num_layers=layers,
                    batch_first=True,
                    dropout=dropout if layers > 1 else 0.0,
                    bidirectional=bidir,
                )
                final_dim = hidden * (2 if bidir else 1)
                self.attn = _Attention(final_dim)
                self.dropout = nn.Dropout(dropout)
                self.head = nn.Linear(final_dim, 1)

            def forward(self, x: Any) -> Tuple[Any, Any]:
                seq_out, _ = self.rnn(x)
                context, weights = self.attn(seq_out)
                context = self.dropout(context)
                logits = self.head(context)
                return logits.squeeze(-1), weights

        return Net()

    def fit(self, X: np.ndarray, y: np.ndarray, epochs: int = 5, lr: float = 1e-3, batch_size: int = 64) -> None:
        dataset = torch.utils.data.TensorDataset(
            torch.tensor(X, dtype=torch.float32), torch.tensor(y, dtype=torch.float32)
        )
        loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)
        criterion = nn.BCEWithLogitsLoss()
        optimizer = optim.Adam(self.model.parameters(), lr=lr)
        self.model.train()
        for epoch in range(epochs):
            epoch_loss = 0.0
            for batch_x, batch_y in loader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)
                optimizer.zero_grad()
                logits, _ = self.model(batch_x)
                loss = criterion(logits, batch_y)
                loss.backward()
                optimizer.step()
                epoch_loss += float(loss.item())
            log.debug("temporal_epoch", epoch=epoch, loss=round(epoch_loss / len(loader), 4))

    def predict_proba(self, X: np.ndarray, mc_runs: int = 0, keep_dropout: bool = False) -> np.ndarray:
        self.model.eval()
        with torch.no_grad():
            x_tensor = torch.tensor(X, dtype=torch.float32).to(self.device)
            logits, _ = self.model(x_tensor)
            probs = torch.sigmoid(logits).cpu().numpy()
        base_probs = np.column_stack([1 - probs, probs])
        if mc_runs > 0:
            probs_mc = [self._mc_pass(x_tensor) for _ in range(mc_runs)]
            return np.stack([base_probs] + probs_mc, axis=0)
        return base_probs

    def _mc_pass(self, x_tensor: Any) -> np.ndarray:
        self.model.train()  # enable dropout
        with torch.no_grad():
            logits, _ = self.model(x_tensor)
            probs = torch.sigmoid(logits).cpu().numpy()
        self.model.eval()
        return np.column_stack([1 - probs, probs])

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        probs = self.predict_proba(X)[:, 1]
        return (probs >= threshold).astype(int)

    def explain(self, X: np.ndarray, sample_size: int = 256) -> Any:
        try:
            x_sample = X[:sample_size]
            _, weights = self.model(torch.tensor(x_sample, dtype=torch.float32).to(self.device))
            return {"attention_weights": weights.detach().cpu().numpy()}
        except Exception as exc:  # noqa: BLE001
            log.warning("temporal_explain_failed", error=str(exc))
            return None

    def estimate_uncertainty(self, X: np.ndarray, mc_runs: int = 10) -> UncertaintyBreakdown:
        probs_mc = self.predict_proba(X, mc_runs=mc_runs)
        if probs_mc.ndim == 2:
            probs_mean = probs_mc.mean(axis=0)
            return UncertaintyBreakdown(entropy=entropy_from_probs(probs_mean))
        probs_last = probs_mc[:, :, 1]  # [mc, batch]
        mean_prob = probs_last.mean(axis=0)
        std_prob = probs_last.std(axis=0)
        entropies = [entropy_from_probs(np.array([p, 1 - p])) for p in mean_prob]
        entropy = float(np.mean(entropies)) if entropies else None
        return UncertaintyBreakdown(
            entropy=entropy,
            mc_dropout_std=float(std_prob.mean()),
            metadata={"mc_runs": mc_runs},
        )

    def predict_with_filters(
        self, X: np.ndarray, confidence_threshold: float = 0.6, uncertainty_threshold: float = 0.1
    ) -> PredictionResult:
        probs = self.predict_proba(X)
        mean_probs = probs if probs.ndim == 2 else probs.mean(axis=0)
        conf = confidence_from_probs(mean_probs[0]) if len(mean_probs) else None
        uncert = self.estimate_uncertainty(X)
        allowed = (conf or 0) >= confidence_threshold and (uncert.mc_dropout_std or 0) <= uncertainty_threshold
        return PredictionResult(
            prediction=(mean_probs[:, 1] >= confidence_threshold).astype(int) if probs.ndim == 2 else None,
            probabilities=mean_probs,
            confidence=conf,
            uncertainty=uncert,
            metadata={"allowed": allowed},
        )
