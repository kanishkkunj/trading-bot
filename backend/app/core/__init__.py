"""app.core package — cross-cutting infrastructure: feature flags, metrics, guards."""

from app.core.feature_flags import (
    ingestion_hardening_enabled,
    is_enabled,
    options_signals_enabled,
    override_flag,
    strict_freshness_enabled,
    walk_forward_gate_enabled,
)
from app.core.baseline_metrics import BaselineMetrics, Snapshot, metrics

__all__ = [
    "is_enabled",
    "override_flag",
    "ingestion_hardening_enabled",
    "options_signals_enabled",
    "strict_freshness_enabled",
    "walk_forward_gate_enabled",
    "BaselineMetrics",
    "Snapshot",
    "metrics",
]
