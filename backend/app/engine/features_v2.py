"""Institutional-grade feature engineering with point-in-time correctness."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

try:  # optional redis cache
    import redis.asyncio as redis
except Exception:  # noqa: BLE001
    redis = None  # type: ignore


@dataclass
class FeatureVersion:
    name: str
    version: str = "2.0"


class FeatureStore:
    """Feature cache backed by Redis (optional)."""

    def __init__(self, redis_url: Optional[str] = None, ttl: int = 3600):
        self.ttl = ttl
        self.redis = redis.Redis.from_url(redis_url) if redis_url and redis else None

    async def get(self, key: str) -> Optional[pd.DataFrame]:
        if not self.redis:
            return None
        raw = await self.redis.get(key)
        if not raw:
            return None
        return pd.read_json(raw, orient="split")

    async def set(self, key: str, df: pd.DataFrame) -> None:
        if not self.redis:
            return
        await self.redis.set(key, df.to_json(orient="split"), ex=self.ttl)


class FeatureEngineerV2:
    def __init__(self, feature_store: Optional[FeatureStore] = None):
        self.feature_store = feature_store
        self.meta = FeatureVersion(name="features_v2")

    async def compute_online(
        self,
        ohlcv: pd.DataFrame,
        sector: Optional[pd.Series] = None,
        options: Optional[pd.DataFrame] = None,
        events: Optional[pd.DataFrame] = None,
        cache_key: Optional[str] = None,
    ) -> pd.DataFrame:
        if cache_key and self.feature_store:
            cached = await self.feature_store.get(cache_key)
            if cached is not None:
                return cached
        feats = self._compute_all(ohlcv.copy(), sector, options, events)
        if cache_key and self.feature_store:
            await self.feature_store.set(cache_key, feats)
        return feats

    def compute_offline(
        self,
        ohlcv: pd.DataFrame,
        sector: Optional[pd.Series] = None,
        options: Optional[pd.DataFrame] = None,
        events: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        return self._compute_all(ohlcv.copy(), sector, options, events)

    def _compute_all(
        self,
        df: pd.DataFrame,
        sector: Optional[pd.Series],
        options: Optional[pd.DataFrame],
        events: Optional[pd.DataFrame],
    ) -> pd.DataFrame:
        # Expect columns: ["open","high","low","close","volume","bid","ask","bid_size","ask_size","vwap"] (bid/ask optional)
        df = df.sort_index()
        df = df.copy()

        # Realized volatility estimators
        df["rv_parkinson"] = (1.0 / (4 * math.log(2))) * (np.log(df["high"] / df["low"])) ** 2
        df["rv_garman_klass"] = 0.5 * (np.log(df["high"] / df["low"])) ** 2 - (2 * math.log(2) - 1) * (
            np.log(df["close"] / df["open"])
        )
        df["rv_rogers_satchell"] = np.log(df["high"] / df["close"]) * np.log(df["high"] / df["open"]) + np.log(
            df["low"] / df["close"]
        ) * np.log(df["low"] / df["open"])

        # Bid/ask bounce proxy
        if {"bid", "ask"}.issubset(df.columns):
            mid = (df["bid"] + df["ask"]) / 2
            df["mid"] = mid
            df["mid_ret"] = df["mid"].pct_change()
            df["bounce"] = df["mid_ret"] * df["mid_ret"].shift(1)
        else:
            df["mid"] = df["close"]
            df["mid_ret"] = df["close"].pct_change()
            df["bounce"] = df["mid_ret"] * df["mid_ret"].shift(1)

        # Order book imbalance (L1 proxy if no depth)
        if {"bid_size", "ask_size"}.issubset(df.columns):
            df["obi"] = (df["bid_size"] - df["ask_size"]) / (df["bid_size"] + df["ask_size"].replace(0, np.nan))
        else:
            df["obi"] = np.nan

        # Kyle lambda and Amihud illiquidity
        df["ret"] = df["close"].pct_change()
        df["dollar_vol"] = df["close"] * df["volume"]
        df["kyle_lambda"] = (df["ret"] / df["volume"].replace(0, np.nan)).rolling(20).mean()
        df["amihud"] = (df["ret"].abs() / df["dollar_vol"].replace(0, np.nan)).rolling(20).mean()

        # VPIN approximation using volume buckets
        df["signed_vol"] = np.sign(df["ret"].fillna(0)) * df["volume"]
        df["vpin"] = (
            df["signed_vol"].rolling(50).sum().abs() / df["volume"].rolling(50).sum().replace(0, np.nan)
        )

        # Sector beta and residual momentum
        if sector is not None:
            aligned = sector.reindex(df.index).fillna(method="ffill")
            cov = df["ret"].rolling(60).cov(aligned.pct_change())
            var = aligned.pct_change().rolling(60).var()
            df["beta_sector"] = cov / var.replace(0, np.nan)
            df["residual_ret"] = df["ret"] - (df["beta_sector"] * aligned.pct_change())
            df["residual_mom"] = df["residual_ret"].rolling(20).sum()
            df["corr_sector"] = df["ret"].rolling(60).corr(aligned.pct_change())
        else:
            df["beta_sector"] = np.nan
            df["residual_mom"] = np.nan
            df["corr_sector"] = np.nan

        # Lead-lag with sector: correlation of stock leading sector by 1 day
        if sector is not None:
            df["lead_lag"] = df["ret"].shift(1).rolling(20).corr(aligned.pct_change())
        else:
            df["lead_lag"] = np.nan

        # Options-derived
        if options is not None and not options.empty:
            options = options.copy()
            if "iv" in options:
                iv = options["iv"].reindex(df.index)
                df["iv"] = iv
                df["iv_rank"] = iv.rolling(252).apply(lambda x: x.rank().iloc[-1] / len(x) if len(x.dropna()) else np.nan)
                df["iv_percentile"] = iv.rolling(252).apply(
                    lambda x: (x <= x.iloc[-1]).mean() if len(x.dropna()) else np.nan
                )
            if {"call_iv", "put_iv"}.issubset(options.columns):
                call_iv = options["call_iv"].reindex(df.index)
                put_iv = options["put_iv"].reindex(df.index)
                df["rr_25d"] = call_iv - put_iv
            if {"front_iv", "back_iv"}.issubset(options.columns):
                front = options["front_iv"].reindex(df.index)
                back = options["back_iv"].reindex(df.index)
                df["term_slope"] = back - front
            if {"pc_ratio", "pc_volume"}.issubset(options.columns):
                pc = options["pc_ratio"].reindex(df.index)
                vol = options["pc_volume"].reindex(df.index)
                df["pc_mom"] = pc.pct_change(5)
                df["unusual_opt_vol"] = (vol - vol.rolling(20).mean()) / vol.rolling(20).std()
        else:
            df["iv_rank"] = np.nan
            df["iv_percentile"] = np.nan
            df["rr_25d"] = np.nan
            df["term_slope"] = np.nan
            df["pc_mom"] = np.nan
            df["unusual_opt_vol"] = np.nan

        # Temporal/Calendar
        df["day_of_week"] = df.index.dayofweek
        df["tod_min"] = df.index.hour * 60 + df.index.minute
        df["open_range_ret"] = (df["high"] - df["low"]).rolling(30).mean()
        df["dow_seasonality"] = df.groupby("day_of_week")["ret"].transform(lambda x: x - x.mean())

        # Regime detection
        df["adx"] = self._adx(df["high"], df["low"], df["close"], period=14)
        df["cmf"] = self._cmf(df, period=20)
        df["bb_width"] = self._bb_width(df["close"], period=20)
        df["hurst"] = df["close"].rolling(100).apply(self._hurst, raw=True)

        # Drop rows with insufficient history to avoid look-ahead bias leaks
        df = df.dropna().copy()

        # Redundancy pruning via correlation threshold
        df = self._prune_correlated(df, threshold=0.95)
        df["feature_version"] = self.meta.version
        return df

    @staticmethod
    def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        up = high.diff()
        down = -low.diff()
        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)
        tr = pd.concat([(high - low), (high - close.shift()), (close.shift() - low)], axis=1).abs().max(axis=1)
        atr = tr.rolling(period).mean()
        plus_di = 100 * pd.Series(plus_dm).rolling(period).mean() / atr
        minus_di = 100 * pd.Series(minus_dm).rolling(period).mean() / atr
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
        return dx.rolling(period).mean()

    @staticmethod
    def _cmf(df: pd.DataFrame, period: int = 20) -> pd.Series:
        mf_mult = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (df["high"] - df["low"] + 1e-9)
        mf_vol = mf_mult * df["volume"]
        return mf_vol.rolling(period).sum() / df["volume"].rolling(period).sum()

    @staticmethod
    def _bb_width(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.Series:
        ma = close.rolling(period).mean()
        std = close.rolling(period).std()
        upper = ma + num_std * std
        lower = ma - num_std * std
        return (upper - lower) / ma

    @staticmethod
    def _hurst(arr: np.ndarray) -> float:
        if len(arr) < 20:
            return np.nan
        ts = pd.Series(arr)
        lags = range(2, min(20, len(ts)))
        tau = [math.sqrt(np.std(ts.diff(lag))) for lag in lags]
        if any(t <= 0 for t in tau):
            return np.nan
        poly = np.polyfit(np.log(lags), np.log(tau), 1)
        return poly[0] * 2.0

    @staticmethod
    def _prune_correlated(df: pd.DataFrame, threshold: float = 0.95) -> pd.DataFrame:
        numeric = df.select_dtypes(include=[np.number]).copy()
        corr = numeric.corr().abs()
        upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
        to_drop = [column for column in upper.columns if any(upper[column] > threshold)]
        return df.drop(columns=to_drop, errors="ignore")
