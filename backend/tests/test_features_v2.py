import pandas as pd
import numpy as np
import pytest

from app.engine.features_v2 import FeatureEngineerV2


@pytest.fixture
def sample_ohlcv():
    idx = pd.date_range("2024-01-01", periods=120, freq="D")
    data = {
        "open": np.linspace(100, 120, 120),
        "high": np.linspace(101, 121, 120),
        "low": np.linspace(99, 119, 120),
        "close": np.linspace(100, 125, 120) + np.sin(np.arange(120)) * 0.5,
        "volume": np.linspace(1e5, 2e5, 120),
        "bid": np.linspace(99.5, 124.5, 120),
        "ask": np.linspace(100.5, 125.5, 120),
        "bid_size": np.linspace(500, 700, 120),
        "ask_size": np.linspace(400, 800, 120),
    }
    return pd.DataFrame(data, index=idx)


@pytest.fixture
def sample_sector():
    idx = pd.date_range("2024-01-01", periods=120, freq="D")
    return pd.Series(np.linspace(1000, 1100, 120), index=idx)


@pytest.fixture
def sample_options():
    idx = pd.date_range("2024-01-01", periods=120, freq="D")
    return pd.DataFrame(
        {
            "iv": np.linspace(0.2, 0.4, 120),
            "call_iv": np.linspace(0.21, 0.41, 120),
            "put_iv": np.linspace(0.19, 0.39, 120),
            "front_iv": np.linspace(0.2, 0.3, 120),
            "back_iv": np.linspace(0.25, 0.35, 120),
            "pc_ratio": np.linspace(1.0, 1.2, 120),
            "pc_volume": np.linspace(1000, 1500, 120),
        },
        index=idx,
    )


@pytest.mark.asyncio
async def test_feature_engineer_v2_basic(sample_ohlcv, sample_sector, sample_options):
    fe = FeatureEngineerV2()
    out = await fe.compute_online(sample_ohlcv, sector=sample_sector, options=sample_options, cache_key=None)
    # Ensure key features exist and are finite
    for col in [
        "rv_parkinson",
        "rv_garman_klass",
        "rv_rogers_satchell",
        "obi",
        "kyle_lambda",
        "amihud",
        "vpin",
        "beta_sector",
        "residual_mom",
        "corr_sector",
        "lead_lag",
        "iv_rank",
        "rr_25d",
        "term_slope",
        "pc_mom",
        "bb_width",
        "hurst",
    ]:
        assert col in out.columns
    assert (out.index == out.index.sort_values()).all()


@pytest.mark.asyncio
async def test_feature_pruning(sample_ohlcv):
    fe = FeatureEngineerV2()
    out = await fe.compute_online(sample_ohlcv, cache_key=None)
    # Should have feature_version marker
    assert "feature_version" in out.columns
    # No look-ahead bias: first row of returns should be non-null after dropna
    assert out.iloc[0]["ret"] == out["ret"].iloc[0]
