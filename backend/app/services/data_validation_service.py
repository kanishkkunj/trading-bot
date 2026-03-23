"""OHLCV candle data validation service.

Adapted from Imp files/data_validator.py to use:
- Lowercase column names that match the app's Candle model (time, open, high, low, close, volume)
- Pure pandas/numpy — no external deps beyond what's already in pyproject.toml
- Dataclass-based report for easy JSON serialization
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class ValidationIssue:
    timestamp: str
    row_index: int
    issue_type: str
    severity: str  # "error" | "warning"
    description: str


@dataclass
class DataValidationReport:
    symbol: str
    total_candles: int
    date_range: Dict[str, Any]
    issues: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]
    statistics: Dict[str, Any]
    validation_status: str  # "ok" | "warning" | "error"


class OHLCVValidator:
    """Validates OHLCV candle data fetched from the database or passed as raw records."""

    def __init__(self) -> None:
        self.df: Optional[pd.DataFrame] = None
        self._time_col: str = "time"
        self.issues: List[ValidationIssue] = []
        self.warnings: List[ValidationIssue] = []

    # ------------------------------------------------------------------ loaders

    def load_from_records(self, records: List[Dict[str, Any]], time_col: str = "time") -> None:
        """Load from a list of candle dicts (as returned by the database or API)."""
        self.df = pd.DataFrame(records)
        self.df[time_col] = pd.to_datetime(self.df[time_col])
        self.df = self.df.sort_values(time_col).reset_index(drop=True)
        self._time_col = time_col
        self.issues = []
        self.warnings = []

    def load_from_dataframe(self, df: pd.DataFrame, time_col: str = "time") -> None:
        """Load from an existing DataFrame."""
        self.df = df.copy()
        self.df[time_col] = pd.to_datetime(self.df[time_col])
        self.df = self.df.sort_values(time_col).reset_index(drop=True)
        self._time_col = time_col
        self.issues = []
        self.warnings = []

    # ------------------------------------------------------------------ validators

    def validate_ohlc_relationships(self) -> Dict[str, Any]:
        """Check High >= Open, Close; Low <= Open, Close; all prices > 0."""
        issues: List[ValidationIssue] = []
        for idx, row in self.df.iterrows():
            ts = str(row[self._time_col])
            if row["high"] < row["low"]:
                issues.append(
                    ValidationIssue(ts, int(idx), "ohlc_high_low", "error",
                                    f"High ({row['high']:.2f}) < Low ({row['low']:.2f})")
                )
            if row["high"] < row["open"] or row["high"] < row["close"]:
                issues.append(
                    ValidationIssue(ts, int(idx), "ohlc_high", "error",
                                    f"High ({row['high']:.2f}) < Open or Close")
                )
            if row["low"] > row["open"] or row["low"] > row["close"]:
                issues.append(
                    ValidationIssue(ts, int(idx), "ohlc_low", "error",
                                    f"Low ({row['low']:.2f}) > Open or Close")
                )
            if row["open"] <= 0 or row["high"] <= 0 or row["low"] <= 0 or row["close"] <= 0:
                issues.append(ValidationIssue(ts, int(idx), "negative_price", "error", "Price <= 0"))

        self.issues.extend(issues)
        return {
            "total_issues": len(issues),
            "valid": len(issues) == 0,
            "issues": [asdict(i) for i in issues[:5]],
        }

    def validate_volume(self) -> Dict[str, Any]:
        """Flag zero/negative volume rows and statistical outliers (>3σ)."""
        issues: List[ValidationIssue] = []
        zero_vol = self.df[self.df["volume"] <= 0]
        for idx, row in zero_vol.iterrows():
            issues.append(
                ValidationIssue(str(row[self._time_col]), int(idx), "zero_volume", "warning",
                                f"Volume is {row['volume']}")
            )

        if len(self.df) > 1:
            vol_mean = self.df["volume"].mean()
            vol_std = self.df["volume"].std()
            if vol_std > 0:
                outliers = self.df[self.df["volume"] > vol_mean + 3 * vol_std]
                for idx, row in outliers.iterrows():
                    self.warnings.append(
                        ValidationIssue(str(row[self._time_col]), int(idx), "volume_outlier", "warning",
                                        f"Volume {int(row['volume'])} is >3σ from mean")
                    )

        self.issues.extend(issues)
        return {
            "zero_volume": len(issues),
            "outlier_count": len(self.warnings),
            "valid": len(issues) == 0,
        }

    def detect_gaps(self, min_gap_days: int = 5) -> Dict[str, Any]:
        """Detect trading-day gaps larger than min_gap_days calendar days."""
        gaps: List[Dict[str, Any]] = []
        df_sorted = self.df.sort_values(self._time_col)
        for i in range(1, len(df_sorted)):
            prev = df_sorted.iloc[i - 1][self._time_col]
            curr = df_sorted.iloc[i][self._time_col]
            gap_days = (curr - prev).days
            if gap_days > min_gap_days:
                gaps.append({"start": str(prev.date()), "end": str(curr.date()), "days": gap_days})
                self.warnings.append(
                    ValidationIssue(str(curr), i, "date_gap", "warning", f"Gap of {gap_days} days")
                )
        return {"gap_count": len(gaps), "gaps": gaps[:5], "has_gaps": len(gaps) > 0}

    def detect_outliers(self, z_threshold: float = 3.0) -> Dict[str, Any]:
        """Flag single-period returns whose Z-score exceeds z_threshold."""
        outliers: List[Dict[str, Any]] = []
        if len(self.df) < 2:
            return {"outlier_count": 0, "outliers": [], "has_outliers": False}

        df_sorted = self.df.sort_values(self._time_col).reset_index(drop=True)
        rets = df_sorted["close"].pct_change()
        r_mean = rets.mean()
        r_std = rets.std()
        if r_std == 0:
            return {"outlier_count": 0, "outliers": [], "has_outliers": False}

        for idx in range(1, len(df_sorted)):
            ret_val = rets.iloc[idx]
            if pd.isna(ret_val):
                continue
            zscore = abs((ret_val - r_mean) / r_std)
            if zscore > z_threshold:
                ts = str(df_sorted.iloc[idx][self._time_col])
                outliers.append({
                    "time": ts,
                    "return_pct": round(float(ret_val * 100), 4),
                    "zscore": round(float(zscore), 4),
                })
                self.warnings.append(
                    ValidationIssue(ts, idx, "price_outlier", "warning",
                                    f"Return {ret_val * 100:.2f}% (Z: {zscore:.2f})")
                )

        return {
            "outlier_count": len(outliers),
            "outliers": outliers[:5],
            "has_outliers": len(outliers) > 0,
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Return summary statistics for the loaded data."""
        if self.df is None or self.df.empty:
            return {}
        return {
            "total_rows": len(self.df),
            "date_range": {
                "start": str(self.df[self._time_col].min()),
                "end": str(self.df[self._time_col].max()),
            },
            "close_stats": {
                "min": float(self.df["close"].min()),
                "max": float(self.df["close"].max()),
                "mean": float(self.df["close"].mean()),
            },
            "volume_stats": {
                "min": int(self.df["volume"].min()),
                "max": int(self.df["volume"].max()),
                "mean": int(self.df["volume"].mean()),
            },
        }

    # ------------------------------------------------------------------ main entry

    def run_full_validation(self, symbol: str = "UNKNOWN") -> DataValidationReport:
        """Run all checks and return a consolidated DataValidationReport."""
        if self.df is None or self.df.empty:
            return DataValidationReport(
                symbol=symbol, total_candles=0, date_range={},
                issues=[], warnings=[], statistics={}, validation_status="error",
            )

        self.validate_ohlc_relationships()
        self.validate_volume()
        self.detect_gaps()
        self.detect_outliers()
        stats = self.get_statistics()

        if self.issues:
            status = "error"
        elif self.warnings:
            status = "warning"
        else:
            status = "ok"

        return DataValidationReport(
            symbol=symbol,
            total_candles=len(self.df),
            date_range=stats.get("date_range", {}),
            issues=[asdict(i) for i in self.issues],
            warnings=[asdict(w) for w in self.warnings],
            statistics=stats,
            validation_status=status,
        )
