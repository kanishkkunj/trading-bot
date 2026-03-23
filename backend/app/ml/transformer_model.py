"""Time-series Transformer for long-range and multi-horizon forecasting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import structlog

from app.ml.base import BaseProbModel, PredictionResult, UncertaintyBreakdown, confidence_from_probs, entropy_from_probs, safe_import

log = structlog.get_logger()

torch = safe_import("torch", "torch")
if torch:
    nn = torch.nn
else:  # pragma: no cover
    nn = None


@dataclass
class TransformerConfig:
    input_dim: int
    model_dim: int = 128
    num_heads: int = 4
    num_layers: int = 3
    dropout: float = 0.1
    seq_len: int = 60
    horizon: int = 1


class PositionalEncoding(nn.Module if nn else object):  # type: ignore[misc]
    def __init__(self, d_model: int, max_len: int = 500) -> None:
        if not nn:  # pragma: no cover
            return
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer("pe", pe)

    def forward(self, x: Any) -> Any:
        return x + self.pe[:, : x.size(1)]


class TransformerModel(BaseProbModel):
    """Transformer encoder for sequence modelling with uncertainty and explainability hooks."""

    def __init__(self, config: TransformerConfig) -> None:
        if not torch:
            raise ImportError("TransformerModel requires torch; install with pip install torch")
        self.config = config
        self.model = self._build_model()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)

    def _build_model(self) -> Any:
        cfg = self.config

        class Net(nn.Module):  # type: ignore[misc]
            def __init__(self) -> None:
                super().__init__()
                self.input_proj = nn.Linear(cfg.input_dim, cfg.model_dim)
                encoder_layer = nn.TransformerEncoderLayer(
                    d_model=cfg.model_dim,
                    nhead=cfg.num_heads,
                    dim_feedforward=cfg.model_dim * 4,
                    dropout=cfg.dropout,
                    batch_first=True,
                )
                self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=cfg.num_layers)
                self.pos_encoding = PositionalEncoding(cfg.model_dim, max_len=cfg.seq_len + cfg.horizon + 5)
                self.dropout = nn.Dropout(cfg.dropout)
                self.head = nn.Linear(cfg.model_dim, cfg.horizon)

            def forward(self, x: Any) -> Any:
                x = self.input_proj(x)
                x = self.pos_encoding(x)
                x = self.transformer(x)
                pooled = x.mean(dim=1)
                out = self.dropout(pooled)
                return self.head(out)

        return Net()

    def fit(self, X: np.ndarray, y: np.ndarray, epochs: int = 5, lr: float = 1e-3, batch_size: int = 64) -> None:
        dataset = torch.utils.data.TensorDataset(
            torch.tensor(X, dtype=torch.float32), torch.tensor(y, dtype=torch.float32)
        )
        loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)
        criterion = nn.BCEWithLogitsLoss() if y.ndim == 1 else nn.MSELoss()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        self.model.train()
        for epoch in range(epochs):
            loss_total = 0.0
            for batch_x, batch_y in loader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)
                optimizer.zero_grad()
                logits = self.model(batch_x)
                target = batch_y if batch_y.ndim > 1 else batch_y.unsqueeze(1)
                loss = criterion(logits.squeeze(), target)
                loss.backward()
                optimizer.step()
                loss_total += float(loss.item())
            log.debug("transformer_epoch", epoch=epoch, loss=round(loss_total / len(loader), 4))

    def predict_proba(self, X: np.ndarray, mc_runs: int = 0) -> np.ndarray:
        self.model.eval()
        with torch.no_grad():
            x_tensor = torch.tensor(X, dtype=torch.float32).to(self.device)
            logits = self.model(x_tensor)
            probs = torch.sigmoid(logits).cpu().numpy()
        base = np.column_stack([1 - probs.squeeze(), probs.squeeze()])
        if mc_runs > 0:
            mc_samples = []
            for _ in range(mc_runs):
                self.model.train()
                with torch.no_grad():
                    logits_mc = self.model(x_tensor)
                    probs_mc = torch.sigmoid(logits_mc).cpu().numpy()
                mc_samples.append(np.column_stack([1 - probs_mc.squeeze(), probs_mc.squeeze()]))
            self.model.eval()
            return np.stack([base] + mc_samples, axis=0)
        return base

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        probs = self.predict_proba(X)
        if probs.ndim == 3:
            probs = probs.mean(axis=0)
        return (probs[:, 1] >= threshold).astype(int)

    def explain(self, X: np.ndarray, sample_size: int = 128) -> Any:
        try:
            x_sample = torch.tensor(X[:sample_size], dtype=torch.float32).to(self.device)
            x_sample.requires_grad = True
            logits = self.model(x_sample).sum()
            logits.backward()
            grads = x_sample.grad.detach().cpu().numpy()
            return {"input_gradients": grads}
        except Exception as exc:  # noqa: BLE001
            log.warning("transformer_explain_failed", error=str(exc))
            return None

    def estimate_uncertainty(self, X: np.ndarray, mc_runs: int = 10) -> UncertaintyBreakdown:
        probs = self.predict_proba(X, mc_runs=mc_runs)
        if probs.ndim == 2:
            return UncertaintyBreakdown(entropy=entropy_from_probs(probs.mean(axis=0)))
        probs_last = probs[:, :, 1]
        mean_prob = probs_last.mean(axis=0)
        std_prob = probs_last.std(axis=0)
        entropies = [entropy_from_probs(np.array([p, 1 - p])) for p in mean_prob]
        return UncertaintyBreakdown(
            entropy=float(np.mean(entropies)) if entropies else None,
            mc_dropout_std=float(std_prob.mean()),
            metadata={"mc_runs": mc_runs},
        )

    def predict_with_filters(
        self, X: np.ndarray, confidence_threshold: float = 0.6, uncertainty_threshold: float = 0.1
    ) -> PredictionResult:
        probs = self.predict_proba(X, mc_runs=5)
        probs_mean = probs.mean(axis=0) if probs.ndim == 3 else probs
        conf = confidence_from_probs(probs_mean[0]) if len(probs_mean) else None
        uncert = self.estimate_uncertainty(X, mc_runs=5)
        allowed = (conf or 0) >= confidence_threshold and (uncert.mc_dropout_std or 0) <= uncertainty_threshold
        return PredictionResult(
            prediction=(probs_mean[:, 1] >= confidence_threshold).astype(int),
            probabilities=probs_mean,
            confidence=conf,
            uncertainty=uncert,
            metadata={"allowed": allowed},
        )
