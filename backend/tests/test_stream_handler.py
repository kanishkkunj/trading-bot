import pytest

from app.data_ingestion.stream_handler import StreamHandler


@pytest.mark.asyncio
async def test_order_flow_imbalance_empty():
    handler = StreamHandler(url="wss://example", symbols=["ABC"])
    assert handler.order_flow_imbalance("ABC") == 0.0


@pytest.mark.asyncio
async def test_vpin_empty():
    handler = StreamHandler(url="wss://example", symbols=["ABC"])
    assert handler.vpin("ABC") == 0.0
