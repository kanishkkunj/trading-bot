#!/usr/bin/env python3
"""Train strict NIFTY50 next-day direction model using 20y daily data from yfinance."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import structlog
import yfinance as yf
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    precision_recall_fscore_support,
    roc_auc_score,
)


# Ensure backend/app is in sys.path for module resolution
BACKEND_APP = Path(__file__).parent.parent / "backend" / "app"
if str(BACKEND_APP) not in sys.path:
    sys.path.insert(0, str(BACKEND_APP))

from app.engine.features import FeatureEngine
from app.engine.model import MLModel

log = structlog.get_logger()

# NIFTY50 heavyweights (stable subset to avoid symbol churn)
NIFTY50_TICKERS: List[str] = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "INFY.NS",
    "KOTAKBANK.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "ITC.NS",
    "LT.NS",
    "BAJFINANCE.NS",
    "HINDUNILVR.NS",
    "AXISBANK.NS",
    "ASIANPAINT.NS",
    "MARUTI.NS",
    "SUNPHARMA.NS",
    "TITAN.NS",
    "ULTRACEMCO.NS",
    "WIPRO.NS",
    "POWERGRID.NS",
    "HCLTECH.NS",
    "NTPC.NS",
    "ONGC.NS",
    "JSWSTEEL.NS",
    "TECHM.NS",
    "M&M.NS",
    "NESTLEIND.NS",
    "BRITANNIA.NS",
    "CIPLA.NS",
    "GRASIM.NS",
]

START_DATE = dt.date.today().replace(year=dt.date.today().year - 20)
END_DATE = dt.date.today()
ARTIFACT_PATH = Path(__file__).parent.parent / "backend" / "app" / "engine" / "artifacts" / "xgb_nifty50.bin"


def fetch_ohlcv(ticker: str) -> pd.DataFrame:
    """Download daily OHLCV for a single ticker."""
    df = yf.download(
        ticker,
        start=START_DATE.isoformat(),
        end=END_DATE.isoformat(),
        interval="1d",
        auto_adjust=False,
        progress=False,
    )
    if df.empty:
        raise ValueError(f"No data for {ticker}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0].lower() for col in df.columns]
    else:
        df.columns = [str(col).lower() for col in df.columns]

    df = df.reset_index().rename(
        columns={
            "Date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "adj close": "adj_close",
            "volume": "volume",
        }
    )
    df["ticker"] = ticker
    df = df.sort_values("date").reset_index(drop=True)
    return df


def build_dataset(tickers: List[str], up_bps: float, drop_abs_bps: float) -> pd.DataFrame:
    """Fetch, feature, and label data for all tickers with thresholded labels."""
    up_threshold = up_bps / 10_000.0
    drop_threshold = drop_abs_bps / 10_000.0 if drop_abs_bps > 0 else 0.0
    fe = FeatureEngine()
    frames: list[pd.DataFrame] = []

    for symbol in tickers:
        try:
            raw = fetch_ohlcv(symbol)
            feats = fe.compute_features(raw)
            feats["next_return"] = feats.groupby("ticker")["close_pct_change"].shift(-1)
            feats["target"] = (feats["next_return"] > up_threshold).astype(int)
            if drop_abs_bps > 0:
                feats = feats[feats["next_return"].abs() >= drop_threshold]
            feats = feats.dropna(subset=["target", "next_return"])
            feats = feats.drop(columns=["next_return"])
            frames.append(feats)
            log.info("fetched", ticker=symbol, rows=len(feats))
        except Exception as exc:  # noqa: BLE001
            log.warning("fetch_failed", ticker=symbol, error=str(exc))

    if not frames:
        raise RuntimeError("No data collected for any ticker")

    data = pd.concat(frames, ignore_index=True)
    data = data.sort_values("date").reset_index(drop=True)
    return data


def train_strict_model(df: pd.DataFrame) -> None:
    """Train XGBoost classifier on time-ordered split and persist artifact."""
    feature_cols = [col for col in df.columns if col not in {"date", "ticker", "target"}]

    # Time-based split: last ~2 years for test
    cutoff_date = df["date"].max() - pd.Timedelta(days=730)
    train_df = df[df["date"] <= cutoff_date]
    test_df = df[df["date"] > cutoff_date]

    # Per-symbol standardization using train statistics only
    scale_cols = [c for c in feature_cols if c not in {"dow", "month"}]
    ticker_stats = {}
    for ticker, group in train_df.groupby("ticker"):
        means = group[scale_cols].mean()
        stds = group[scale_cols].std().replace(0, 1.0)
        ticker_stats[ticker] = (means, stds)

    def apply_stats(frame: pd.DataFrame) -> pd.DataFrame:
        normalized = frame.copy()
        for ticker, (means, stds) in ticker_stats.items():
            mask = normalized["ticker"] == ticker
            if not mask.any():
                continue
            normalized.loc[mask, scale_cols] = (
                normalized.loc[mask, scale_cols] - means
            ) / stds
        return normalized

    # Time-aware CV (3 folds of 1 year) on train set with a small param grid
    def build_time_splits(dates: pd.Series, val_span_days: int = 365, n_folds: int = 3) -> list[tuple[pd.Series, pd.Series]]:
        max_date = dates.max()
        splits: list[tuple[pd.Series, pd.Series]] = []
        for i in range(n_folds):
            val_end = max_date - pd.Timedelta(days=i * val_span_days)
            val_start = val_end - pd.Timedelta(days=val_span_days)
            train_mask = dates < val_start
            val_mask = (dates >= val_start) & (dates < val_end)
            if train_mask.sum() > 500 and val_mask.sum() > 200:
                splits.append((train_mask, val_mask))
        return splits

    splits = build_time_splits(train_df["date"], val_span_days=365, n_folds=3)

    param_grid = [
        {"max_depth": 4, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8, "n_estimators": 400, "min_child_weight": 1.0},
        {"max_depth": 5, "learning_rate": 0.03, "subsample": 0.9, "colsample_bytree": 0.9, "n_estimators": 600, "min_child_weight": 3.0},
        {"max_depth": 3, "learning_rate": 0.1, "subsample": 0.7, "colsample_bytree": 0.7, "n_estimators": 300, "min_child_weight": 1.0},
    ]

    best_params = None
    best_auc = -np.inf

    for params in param_grid:
        fold_aucs = []
        for train_mask, val_mask in splits:
            train_fold = train_df.loc[train_mask]
            val_fold = train_df.loc[val_mask]

            train_norm = apply_stats(train_fold)
            val_norm = apply_stats(val_fold)

            X_tr = train_norm[feature_cols]
            y_tr = train_norm["target"].astype(int)
            X_val = val_norm[feature_cols]
            y_val = val_norm["target"].astype(int)

            model = MLModel(model_version="nifty50-dir-v1", **params)
            model.train(X_tr, y_tr)
            y_val_proba = model.predict_proba(X_val)[:, 1]
            auc = roc_auc_score(y_val, y_val_proba)
            fold_aucs.append(auc)

        mean_auc = float(np.mean(fold_aucs)) if fold_aucs else -np.inf
        log.info("cv_result", params=params, mean_auc=round(mean_auc, 4), folds=len(fold_aucs))
        if mean_auc > best_auc:
            best_auc = mean_auc
            best_params = params

    if not best_params:
        best_params = param_grid[0]
        log.warning("cv_fallback", reason="no_valid_folds", chosen=best_params)
    else:
        log.info("cv_best", params=best_params, mean_auc=round(best_auc, 4))

    train_df = apply_stats(train_df)
    test_df = apply_stats(test_df)

    # Threshold tuning on a recent slice of the training data (last 180 days)
    cal_span = pd.Timedelta(days=180)
    cal_mask = train_df["date"] > (train_df["date"].max() - cal_span)
    cal_df = train_df[cal_mask]
    core_df = train_df[~cal_mask]
    if cal_df.empty or core_df.empty:
        cal_df = train_df.tail(2000)
        core_df = train_df.drop(cal_df.index)

    model_cal = MLModel(model_version="nifty50-dir-v1", **best_params)
    model_cal.train(core_df[feature_cols], core_df["target"].astype(int))
    cal_proba = model_cal.predict_proba(cal_df[feature_cols])[:, 1]
    cal_y = cal_df["target"].astype(int)

    best_thr = 0.5
    best_f1 = -np.inf
    for thr in np.linspace(0.45, 0.60, 7):
        preds = (cal_proba >= thr).astype(int)
        if preds.max() == preds.min():
            continue
        f1 = precision_recall_fscore_support(cal_y, preds, average="binary")[2]
        if f1 > best_f1:
            best_f1 = f1
            best_thr = float(thr)

    log.info("threshold_tuning", best_threshold=round(best_thr, 3), cal_size=len(cal_df), f1=round(best_f1, 4))

    X_train = train_df[feature_cols]
    y_train = train_df["target"].astype(int)
    X_test = test_df[feature_cols]
    y_test = test_df["target"].astype(int)

    model = MLModel(model_version="nifty50-dir-v1")
    model.decision_threshold = best_thr
    eval_set = [(X_test, y_test)]  # strict eval on forward window
    model.train(X_train, y_train, eval_set=eval_set)

    # Evaluation
    y_proba = model.predict_proba(X_test)[:, 1]
    y_pred = (y_proba >= best_thr).astype(int)

    acc = accuracy_score(y_test, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(y_test, y_pred, average="binary")
    auc = roc_auc_score(y_test, y_proba)

    log.info(
        "eval",
        accuracy=round(acc, 4),
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        auc=round(auc, 4),
        test_samples=len(y_test),
    )
    log.info("classification_report\n" + classification_report(y_test, y_pred, digits=4))

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(ARTIFACT_PATH))
    log.info("saved_model", path=str(ARTIFACT_PATH))


def main() -> None:
    parser = argparse.ArgumentParser(description="Train NIFTY50 next-day direction model")
    parser.add_argument("--up-bps", type=float, default=25.0, help="Label positive if next return > up_bps (e.g., 25 bps = 0.25%)")
    parser.add_argument("--drop-abs-bps", type=float, default=5.0, help="Drop samples with |next return| below this (e.g., 5 bps). Set 0 to keep all.")
    args = parser.parse_args()

    log.info(
        "starting_download",
        tickers=len(NIFTY50_TICKERS),
        start=str(START_DATE),
        end=str(END_DATE),
        up_bps=args.up_bps,
        drop_abs_bps=args.drop_abs_bps,
    )
    df = build_dataset(NIFTY50_TICKERS, up_bps=args.up_bps, drop_abs_bps=args.drop_abs_bps)
    log.info(
        "dataset_ready",
        rows=len(df),
        start=str(df["date"].min().date()),
        end=str(df["date"].max().date()),
        up_bps=args.up_bps,
        drop_abs_bps=args.drop_abs_bps,
    )
    train_strict_model(df)


if __name__ == "__main__":
    main()
