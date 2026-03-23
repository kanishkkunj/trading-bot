#!/usr/bin/env python3
"""Train strict NIFTY50 next-day direction model using 20y daily data from yfinance."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import List

import joblib
import numpy as np
import pandas as pd
import structlog
import yfinance as yf
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    precision_recall_fscore_support,
    roc_auc_score,
)


# Ensure backend/app is in sys.path for module resolution
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "app"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.engine.features import FeatureEngine
from app.engine.model import MLModel

log = structlog.get_logger()

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
ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_PATH = ROOT / "app" / "engine" / "artifacts" / "xgb_nifty50.bin"
SHORT_ARTIFACT_PATH = ROOT / "app" / "engine" / "artifacts" / "xgb_nifty50_short.bin"
ENSEMBLE_ARTIFACT_PATH = ROOT / "app" / "engine" / "artifacts" / "xgb_nifty50_ensemble.bin"


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

    # Flatten yfinance MultiIndex columns (Price, Ticker)
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

    # Long-horizon model (baseline)
    cal_span = pd.Timedelta(days=180)
    cal_mask = train_df["date"] > (train_df["date"].max() - cal_span)
    cal_df = train_df[cal_mask]
    core_df = train_df[~cal_mask]
    if cal_df.empty or core_df.empty:
        cal_df = train_df.tail(2000)
        core_df = train_df.drop(cal_df.index)

    model_long = MLModel(model_version="nifty50-dir-v1", **best_params)
    model_long.train(core_df[feature_cols], core_df["target"].astype(int))
    raw_cal_long = model_long.model.predict_proba(cal_df[feature_cols])[:, 1]
    calibrator_long = IsotonicRegression(out_of_bounds="clip")
    calibrator_long.fit(raw_cal_long, cal_df["target"].astype(int))
    model_long.calibrator = calibrator_long
    cal_proba_long = model_long.predict_proba(cal_df[feature_cols])[:, 1]
    cal_y = cal_df["target"].astype(int)

    best_thr_long = 0.5
    best_f1_long = -np.inf
    for thr in np.linspace(0.50, 0.65, 7):
        preds = (cal_proba_long >= thr).astype(int)
        if preds.max() == preds.min():
            continue
        f1 = precision_recall_fscore_support(cal_y, preds, average="binary")[2]
        if f1 > best_f1_long:
            best_f1_long = f1
            best_thr_long = float(thr)

    log.info(
        "threshold_tuning_long",
        best_threshold=round(best_thr_long, 3),
        cal_size=len(cal_df),
        f1=round(best_f1_long, 4),
    )

    X_test = test_df[feature_cols]
    y_test = test_df["target"].astype(int)

    model_long.decision_threshold = best_thr_long
    y_proba_long = model_long.predict_proba(X_test)[:, 1]
    y_pred_long = (y_proba_long >= best_thr_long).astype(int)

    acc_long = accuracy_score(y_test, y_pred_long)
    precision_long, recall_long, f1_long, _ = precision_recall_fscore_support(y_test, y_pred_long, average="binary")
    auc_long = roc_auc_score(y_test, y_proba_long)

    log.info(
        "eval_long",
        accuracy=round(acc_long, 4),
        precision=round(precision_long, 4),
        recall=round(recall_long, 4),
        f1=round(f1_long, 4),
        auc=round(auc_long, 4),
        test_samples=len(y_test),
    )

    # Short-horizon model (recent regime focus)
    short_window_days = 3 * 365
    short_train_mask = train_df["date"] >= (train_df["date"].max() - pd.Timedelta(days=short_window_days))
    short_train_df = train_df[short_train_mask]
    if len(short_train_df) < 2000:
        short_train_df = train_df.tail(2000)

    short_cal_span = pd.Timedelta(days=120)
    short_cal_mask = short_train_df["date"] > (short_train_df["date"].max() - short_cal_span)
    short_cal_df = short_train_df[short_cal_mask]
    short_core_df = short_train_df[~short_cal_mask]
    if short_cal_df.empty or short_core_df.empty:
        short_cal_df = short_train_df.tail(1500)
        short_core_df = short_train_df.drop(short_cal_df.index)

    short_params = {**best_params, "learning_rate": max(0.07, best_params.get("learning_rate", 0.05))}
    model_short = MLModel(model_version="nifty50-short-v1", **short_params)
    model_short.train(short_core_df[feature_cols], short_core_df["target"].astype(int))
    raw_cal_short = model_short.model.predict_proba(short_cal_df[feature_cols])[:, 1]
    calibrator_short = IsotonicRegression(out_of_bounds="clip")
    calibrator_short.fit(raw_cal_short, short_cal_df["target"].astype(int))
    model_short.calibrator = calibrator_short

    cal_proba_short = model_short.predict_proba(short_cal_df[feature_cols])[:, 1]
    cal_y_short = short_cal_df["target"].astype(int)

    best_thr_short = 0.5
    best_f1_short = -np.inf
    for thr in np.linspace(0.50, 0.65, 7):
        preds = (cal_proba_short >= thr).astype(int)
        if preds.max() == preds.min():
            continue
        f1 = precision_recall_fscore_support(cal_y_short, preds, average="binary")[2]
        if f1 > best_f1_short:
            best_f1_short = f1
            best_thr_short = float(thr)

    log.info(
        "threshold_tuning_short",
        best_threshold=round(best_thr_short, 3),
        cal_size=len(short_cal_df),
        f1=round(best_f1_short, 4),
    )

    model_short.decision_threshold = best_thr_short
    y_proba_short = model_short.predict_proba(X_test)[:, 1]
    y_pred_short = (y_proba_short >= best_thr_short).astype(int)

    acc_short = accuracy_score(y_test, y_pred_short)
    precision_short, recall_short, f1_short, _ = precision_recall_fscore_support(y_test, y_pred_short, average="binary")
    auc_short = roc_auc_score(y_test, y_proba_short)

    log.info(
        "eval_short",
        accuracy=round(acc_short, 4),
        precision=round(precision_short, 4),
        recall=round(recall_short, 4),
        f1=round(f1_short, 4),
        auc=round(auc_short, 4),
        test_samples=len(y_test),
    )

    # Ensemble (simple average of calibrated probs)
    cal_proba_ensemble = 0.5 * (cal_proba_long + model_short.predict_proba(cal_df[feature_cols])[:, 1])
    best_thr_ensemble = 0.5
    best_f1_ensemble = -np.inf
    for thr in np.linspace(0.50, 0.65, 7):
        preds = (cal_proba_ensemble >= thr).astype(int)
        if preds.max() == preds.min():
            continue
        f1 = precision_recall_fscore_support(cal_y, preds, average="binary")[2]
        if f1 > best_f1_ensemble:
            best_f1_ensemble = f1
            best_thr_ensemble = float(thr)

    log.info(
        "threshold_tuning_ensemble",
        best_threshold=round(best_thr_ensemble, 3),
        cal_size=len(cal_df),
        f1=round(best_f1_ensemble, 4),
    )

    y_proba_ensemble = 0.5 * (y_proba_long + y_proba_short)
    y_pred_ensemble = (y_proba_ensemble >= best_thr_ensemble).astype(int)

    acc_ensemble = accuracy_score(y_test, y_pred_ensemble)
    precision_ensemble, recall_ensemble, f1_ensemble, _ = precision_recall_fscore_support(
        y_test, y_pred_ensemble, average="binary"
    )
    auc_ensemble = roc_auc_score(y_test, y_proba_ensemble)

    log.info(
        "eval_ensemble",
        accuracy=round(acc_ensemble, 4),
        precision=round(precision_ensemble, 4),
        recall=round(recall_ensemble, 4),
        f1=round(f1_ensemble, 4),
        auc=round(auc_ensemble, 4),
        test_samples=len(y_test),
    )
    log.info("classification_report\n" + classification_report(y_test, y_pred_ensemble, digits=4))

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    model_long.save(str(ARTIFACT_PATH))
    log.info("saved_model_long", path=str(ARTIFACT_PATH))

    model_short.save(str(SHORT_ARTIFACT_PATH))
    log.info("saved_model_short", path=str(SHORT_ARTIFACT_PATH))

    joblib.dump(
        {
            "long": model_long,
            "short": model_short,
            "weights": {"long": 0.5, "short": 0.5},
            "decision_threshold": best_thr_ensemble,
        },
        ENSEMBLE_ARTIFACT_PATH,
    )
    log.info("saved_model_ensemble", path=str(ENSEMBLE_ARTIFACT_PATH))


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
