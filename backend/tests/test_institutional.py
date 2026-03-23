"""Unit tests for institutional intelligence helpers."""

from datetime import datetime, timedelta

from app.institutional import (
    CrowdedTrade,
    FiiDiiTracker,
    FlowSnapshot,
    FundHoldingsTracker,
    HoldingsSnapshot,
    InsiderEvent,
    InsiderTracker,
    SmartMoneyConfluence,
)


def test_fii_dii_tracker_bias() -> None:
    tracker = FiiDiiTracker(lookback=3)
    base_time = datetime.utcnow()
    tracker.ingest(
        FlowSnapshot(
            as_of=base_time - timedelta(days=2),
            fii_cash=100,
            fii_futures=50,
            dii_cash=-20,
            dii_futures=-10,
            sector_flows={"IT": 10},
        )
    )
    tracker.ingest(
        FlowSnapshot(
            as_of=base_time - timedelta(days=1),
            fii_cash=120,
            fii_futures=60,
            dii_cash=-10,
            dii_futures=-5,
            sector_flows={"IT": 20},
        )
    )
    tracker.ingest(
        FlowSnapshot(
            as_of=base_time,
            fii_cash=150,
            fii_futures=80,
            dii_cash=-5,
            dii_futures=-2,
            sector_flows={"IT": 30},
        )
    )

    bias = tracker.smart_money_signal()
    trends = tracker.trend()

    assert bias in {"broad_accumulation", "fii_buy_dii_sell"}
    assert trends.trend_fii > 0


def test_insider_tracker_promoter_and_pledge() -> None:
    tracker = InsiderTracker(window=5, high_pledge=0.4)
    now = datetime.utcnow()
    tracker.ingest(
        InsiderEvent(
            as_of=now - timedelta(days=2),
            symbol="RELIANCE.NS",
            actor="Promoter",
            action="buy",
            quantity=1000,
            value=10_000_000,
            pledge_pct=None,
        )
    )
    tracker.ingest(
        InsiderEvent(
            as_of=now - timedelta(days=1),
            symbol="RELIANCE.NS",
            actor="Promoter",
            action="pledge",
            quantity=0,
            value=0,
            pledge_pct=0.45,
        )
    )

    bias = tracker.promoter_bias("RELIANCE.NS")
    pledge = tracker.pledge_risk("RELIANCE.NS")
    flag = tracker.smart_money_flag("RELIANCE.NS")

    assert bias == "promoter_accumulation"
    assert pledge.pledge_pct >= 0.4
    assert flag in {"promoter_accumulation", "high_pledge_risk"}


def test_fund_holdings_crowded_trade() -> None:
    tracker = FundHoldingsTracker()
    tracker.ingest(HoldingsSnapshot(fund="FundA", symbol_weights={"INFY": 0.05, "TCS": 0.03}))
    tracker.ingest(HoldingsSnapshot(fund="FundB", symbol_weights={"INFY": 0.04}))
    tracker.ingest(HoldingsSnapshot(fund="FundC", symbol_weights={"INFY": 0.06}))
    tracker.ingest(HoldingsSnapshot(fund="FundD", symbol_weights={"INFY": 0.07}))
    tracker.ingest(HoldingsSnapshot(fund="FundE", symbol_weights={"INFY": 0.05}))

    crowded = tracker.crowded_trades(min_funds=5, weight_cut=0.02)

    assert any(ct.symbol == "INFY" for ct in crowded)


def test_smart_money_confluence_combines() -> None:
    flows = FiiDiiTracker(lookback=2)
    now = datetime.utcnow()
    flows.ingest(
        FlowSnapshot(
            as_of=now - timedelta(days=1),
            fii_cash=100,
            fii_futures=50,
            dii_cash=20,
            dii_futures=10,
            sector_flows={},
        )
    )
    flows.ingest(
        FlowSnapshot(
            as_of=now,
            fii_cash=150,
            fii_futures=80,
            dii_cash=-30,
            dii_futures=-20,
            sector_flows={},
        )
    )

    insiders = InsiderTracker(window=5)
    insiders.ingest(
        InsiderEvent(
            as_of=now,
            symbol="INFY",
            actor="Promoter",
            action="buy",
            quantity=100,
            value=1_000_000,
            pledge_pct=None,
        )
    )

    holdings = FundHoldingsTracker()
    for f in ["A", "B", "C", "D", "E"]:
        holdings.ingest(HoldingsSnapshot(fund=f, symbol_weights={"INFY": 0.04}))

    confluence = SmartMoneyConfluence(min_crowded_funds=3)
    ctx = confluence.evaluate("INFY", flows=flows, insiders=insiders, holdings=holdings)

    assert ctx.combined in {"strong_buy_signal", "fii_buy_dii_sell", "promoter_accumulation"}
    assert ctx.crowded is True
    assert ctx.symbol == "INFY"
