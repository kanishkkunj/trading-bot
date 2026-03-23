"""Feature engineering module (placeholder for Sprint 2)."""

import pandas as pd
import numpy as np


class FeatureEngine:
    """Feature engineering for ML models."""

    def __init__(self):
        # No stateful params yet; reserved for future config
        pass

    def compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute deterministic, non-leaky features from OHLCV data.

        Expects columns: ['date','ticker','open','high','low','close','volume'] sorted by date.
        Returns a feature DataFrame aligned with input index and without target.
        """

        working = df.copy()

        grouped = working.groupby("ticker", group_keys=False)
        prev_close = grouped["close"].shift(1)

        # Price-based features
        working["close_pct_change"] = working["close"].pct_change()
        working["log_return"] = np.log1p(working["close_pct_change"])

        # Overnight vs intraday dynamics
        working["overnight_return"] = (working["open"] - prev_close) / prev_close
        working["intraday_return"] = (working["close"] - working["open"]) / working["open"]

        for window in (5, 10, 21, 63):
            working[f"return_mean_{window}"] = grouped["log_return"].transform(
                lambda s: s.rolling(window).mean()
            )
            working[f"return_std_{window}"] = grouped["log_return"].transform(
                lambda s: s.rolling(window).std()
            )

        # Rolling z-scores for returns and turnover
        working["logret_z_21"] = grouped["log_return"].transform(
            lambda s: (s - s.rolling(21).mean()) / s.rolling(21).std()
        )

        # Momentum/oscillators
        working["rsi_14"] = self.compute_rsi(working["close"], period=14)
        macd, macd_signal, macd_hist = self.compute_macd(working["close"], 12, 26, 9)
        working["macd"] = macd
        working["macd_signal"] = macd_signal
        working["macd_hist"] = macd_hist

        # Volatility/bands
        upper, sma, lower = self.compute_bollinger_bands(working["close"], 20, 2.0)
        working["bb_upper"] = upper
        working["bb_mid"] = sma
        working["bb_lower"] = lower
        working["bb_width"] = (upper - lower) / sma.replace(0, np.nan)
        working["atr_14"] = self.compute_atr(working["high"], working["low"], working["close"], 14)

        # Trend-following features
        working["ema_20"] = grouped["close"].transform(lambda s: s.ewm(span=20, adjust=False).mean())
        working["sma_50"] = grouped["close"].transform(lambda s: s.rolling(50).mean())
        working["sma_200"] = grouped["close"].transform(lambda s: s.rolling(200).mean())
        working["ema20_sma50_spread"] = (working["ema_20"] - working["sma_50"]) / working["sma_50"].replace(0, np.nan)
        working["sma50_sma200_spread"] = (working["sma_50"] - working["sma_200"]) / working["sma_200"].replace(0, np.nan)
        working["trend_strength_20"] = grouped["close"].transform(
            lambda s: s.pct_change().rolling(20).mean() / s.pct_change().rolling(20).std()
        )

        # Support/resistance proximity using rolling breakout levels
        support_20 = grouped["low"].transform(lambda s: s.rolling(20).min())
        resistance_20 = grouped["high"].transform(lambda s: s.rolling(20).max())
        working["dist_to_support_20"] = (working["close"] - support_20) / working["close"].replace(0, np.nan)
        working["dist_to_resistance_20"] = (resistance_20 - working["close"]) / working["close"].replace(0, np.nan)
        working["breakout_up_20"] = (working["close"] > resistance_20.shift(1)).astype(float)
        working["breakdown_dn_20"] = (working["close"] < support_20.shift(1)).astype(float)

        # Mean-reversion composites
        working["bb_zscore"] = (working["close"] - sma) / ((upper - lower) / 2).replace(0, np.nan)
        working["vwap_dev"] = (working["close"] - working["vwap"]) / working["vwap"].replace(0, np.nan)
        working["mean_reversion_score"] = (
            (-working["bb_zscore"]).fillna(0)
            + ((50.0 - working["rsi_14"]) / 50.0).fillna(0)
            + (-working["logret_z_21"]).fillna(0)
        ) / 3.0

        # Volume features
        working["vol_sma_20"] = working["volume"].rolling(20).mean()
        working["vol_ratio"] = working["volume"] / working["vol_sma_20"]
        working["vwap"] = self.compute_vwap(working["high"], working["low"], working["close"], working["volume"])
        working["turnover"] = working["volume"] * working["close"]
        working["turnover_z_20"] = grouped["turnover"].transform(
            lambda s: (s - s.rolling(20).mean()) / s.rolling(20).std()
        )

        # Cross-sectional context (per date ranks/dispersion)
        working["xs_rank_logret"] = working.groupby("date")["log_return"].rank(pct=True)
        working["xs_dispersion"] = working.groupby("date")["log_return"].transform("std")

        # Calendar context
        working["dow"] = pd.to_datetime(working["date"]).dt.dayofweek
        working["month"] = pd.to_datetime(working["date"]).dt.month

        feature_cols = [
            "close_pct_change",
            "log_return",
            "overnight_return",
            "intraday_return",
            "return_mean_5",
            "return_std_5",
            "return_mean_10",
            "return_std_10",
            "return_mean_21",
            "return_std_21",
            "return_mean_63",
            "return_std_63",
            "logret_z_21",
            "rsi_14",
            "macd",
            "macd_signal",
            "macd_hist",
            "bb_upper",
            "bb_mid",
            "bb_lower",
            "bb_width",
            "atr_14",
            "ema_20",
            "sma_50",
            "sma_200",
            "ema20_sma50_spread",
            "sma50_sma200_spread",
            "trend_strength_20",
            "dist_to_support_20",
            "dist_to_resistance_20",
            "breakout_up_20",
            "breakdown_dn_20",
            "bb_zscore",
            "vwap_dev",
            "mean_reversion_score",
            "vol_ratio",
            "vwap",
            "turnover_z_20",
            "xs_rank_logret",
            "xs_dispersion",
            "dow",
            "month",
        ]

        # Fill benignly for cross-sectional/vol regime signals; then drop rows still missing
        working["xs_dispersion"] = working["xs_dispersion"].fillna(0)
        working["logret_z_21"] = working["logret_z_21"].fillna(0)
        working["turnover_z_20"] = working["turnover_z_20"].fillna(0)

        working = working.dropna(subset=feature_cols).reset_index(drop=True)

        return working[["date", "ticker", *feature_cols]]

    def compute_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Compute RSI indicator."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def compute_macd(
        self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Compute MACD indicator."""
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal).mean()
        macd_hist = macd - macd_signal
        return macd, macd_signal, macd_hist

    def compute_bollinger_bands(
        self, prices: pd.Series, period: int = 20, std_dev: float = 2.0
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Compute Bollinger Bands."""
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return upper, sma, lower

    def compute_atr(
        self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
    ) -> pd.Series:
        """Compute Average True Range."""
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def compute_vwap(
        self, high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
    ) -> pd.Series:
        """Compute Volume Weighted Average Price."""
        typical_price = (high + low + close) / 3
        vwap = (typical_price * volume).cumsum() / volume.cumsum()
        return vwap
