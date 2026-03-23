"""Feature engineering tests."""

import numpy as np
import pandas as pd
import pytest

from app.engine.features import FeatureEngine


@pytest.fixture
def sample_data() -> pd.DataFrame:
    """Create sample OHLCV data."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="D")

    data = pd.DataFrame({
        "open": 100 + np.random.randn(100).cumsum(),
        "high": 102 + np.random.randn(100).cumsum(),
        "low": 98 + np.random.randn(100).cumsum(),
        "close": 100 + np.random.randn(100).cumsum(),
        "volume": np.random.randint(1000000, 10000000, 100),
    }, index=dates)

    return data


def test_compute_rsi(sample_data: pd.DataFrame) -> None:
    """Test RSI calculation."""
    engine = FeatureEngine()

    rsi = engine.compute_rsi(sample_data["close"], period=14)

    assert len(rsi) == len(sample_data)
    assert rsi.iloc[-1] >= 0
    assert rsi.iloc[-1] <= 100


def test_compute_macd(sample_data: pd.DataFrame) -> None:
    """Test MACD calculation."""
    engine = FeatureEngine()

    macd, signal, hist = engine.compute_macd(sample_data["close"])

    assert len(macd) == len(sample_data)
    assert len(signal) == len(sample_data)
    assert len(hist) == len(sample_data)


def test_compute_bollinger_bands(sample_data: pd.DataFrame) -> None:
    """Test Bollinger Bands calculation."""
    engine = FeatureEngine()

    upper, middle, lower = engine.compute_bollinger_bands(sample_data["close"])

    assert len(upper) == len(sample_data)
    assert len(middle) == len(sample_data)
    assert len(lower) == len(sample_data)

    # Upper should be above middle, lower should be below
    assert upper.iloc[-1] >= middle.iloc[-1]
    assert lower.iloc[-1] <= middle.iloc[-1]


def test_compute_atr(sample_data: pd.DataFrame) -> None:
    """Test ATR calculation."""
    engine = FeatureEngine()

    atr = engine.compute_atr(
        sample_data["high"],
        sample_data["low"],
        sample_data["close"],
    )

    assert len(atr) == len(sample_data)
    assert atr.iloc[-1] >= 0


def test_compute_vwap(sample_data: pd.DataFrame) -> None:
    """Test VWAP calculation."""
    engine = FeatureEngine()

    vwap = engine.compute_vwap(
        sample_data["high"],
        sample_data["low"],
        sample_data["close"],
        sample_data["volume"],
    )

    assert len(vwap) == len(sample_data)
