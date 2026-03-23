"""Feature flag registry for phased rollout of new capabilities.

All flags default to False (disabled). Enable via environment variables or by
setting the corresponding field in Settings:

    FEATURE_INGESTION_HARDENING=true   -- Phase 1: NSE retry + staleness detection
    FEATURE_OPTIONS_SIGNALS=true        -- Phase 2/3: OI-pressure options signals
    FEATURE_WALK_FORWARD_GATE=true      -- Phase 4: walk-forward validation gate
    FEATURE_STRICT_FRESHNESS=true       -- Phase 1: hard reject on stale data

Each flag can also be overridden at runtime for testing via `override_flag`.
Overrides are process-local and do not affect Settings or env vars.
"""

from __future__ import annotations

from typing import Dict

import structlog

log = structlog.get_logger()

# --- Runtime overrides (test / admin use only) ------------------------------
_OVERRIDES: Dict[str, bool] = {}


def override_flag(name: str, value: bool) -> None:
    """Temporarily override a flag for the current process lifetime."""
    _OVERRIDES[name] = value
    log.info("feature_flag_override", flag=name, value=value)


def clear_overrides() -> None:
    """Clear all runtime overrides (useful in tests)."""
    _OVERRIDES.clear()


# --- Public API -------------------------------------------------------------

def is_enabled(name: str, default: bool = False) -> bool:
    """Return True if the named feature flag is active.

    Resolution order: runtime override → Settings value → *default*.
    """
    if name in _OVERRIDES:
        return _OVERRIDES[name]

    # Lazy import to avoid circular dependency with config
    try:
        from app.config import get_settings

        settings = get_settings()
        attr = f"FEATURE_{name.upper()}"
        if hasattr(settings, attr):
            return bool(getattr(settings, attr))
    except Exception:  # pragma: no cover
        pass

    return default


# --- Convenience flag accessors ---------------------------------------------

def ingestion_hardening_enabled() -> bool:
    """Phase 1: Retry loops, session refresh, and staleness detection on market data fetches."""
    return is_enabled("INGESTION_HARDENING")


def options_signals_enabled() -> bool:
    """Phase 2/3: OI boundary pressure features and options-chain-derived signals."""
    return is_enabled("OPTIONS_SIGNALS")


def walk_forward_gate_enabled() -> bool:
    """Phase 4: Require walk-forward validation before promoting model/threshold changes."""
    return is_enabled("WALK_FORWARD_GATE")


def strict_freshness_enabled() -> bool:
    """Phase 1: Hard-reject execution when market data is older than the staleness threshold."""
    return is_enabled("STRICT_FRESHNESS")
