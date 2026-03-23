"""Strategy engine tests."""

import pytest

from app.engine.policy import DecisionPolicy, Decision
from app.engine.rules import RuleEngine, TrendFilter
from app.models.signal import SignalAction


def test_decision_policy_buy_signal() -> None:
    """Test decision policy generates buy signal."""
    policy = DecisionPolicy(confidence_threshold=0.6)

    decision = policy.decide(
        ml_score=0.8,
        rules_passed=True,
        current_position=0,
        available_capital=100000.0,
        current_price=1000.0,
    )

    assert decision.action == SignalAction.BUY
    assert decision.confidence == 0.8
    assert decision.suggested_quantity > 0


def test_decision_policy_sell_signal() -> None:
    """Test decision policy generates sell signal."""
    policy = DecisionPolicy(confidence_threshold=0.6)

    decision = policy.decide(
        ml_score=0.2,
        rules_passed=True,
        current_position=10,
        available_capital=100000.0,
        current_price=1000.0,
    )

    assert decision.action == SignalAction.SELL
    assert decision.suggested_quantity == 10


def test_decision_policy_low_confidence() -> None:
    """Test decision policy holds on low confidence."""
    policy = DecisionPolicy(confidence_threshold=0.6)

    decision = policy.decide(
        ml_score=0.5,
        rules_passed=True,
        current_position=0,
        available_capital=100000.0,
        current_price=1000.0,
    )

    assert decision.action == SignalAction.HOLD


def test_decision_policy_rules_failed() -> None:
    """Test decision policy holds when rules fail."""
    policy = DecisionPolicy(confidence_threshold=0.6)

    decision = policy.decide(
        ml_score=0.8,
        rules_passed=False,
        current_position=0,
        available_capital=100000.0,
        current_price=1000.0,
    )

    assert decision.action == SignalAction.HOLD
    assert "Rules filter" in decision.reason


def test_rule_engine_add_rule() -> None:
    """Test adding rules to rule engine."""
    engine = RuleEngine()

    engine.add_rule("test_rule", lambda x: True)

    assert len(engine.rules) == 1
    assert engine.rules[0]["name"] == "test_rule"


def test_rule_engine_evaluate() -> None:
    """Test rule engine evaluation."""
    engine = RuleEngine()

    engine.add_rule("always_true", lambda x: True)
    engine.add_rule("always_false", lambda x: False)

    results = engine.evaluate({})

    assert results["always_true"] is True
    assert results["always_false"] is False


def test_rule_engine_should_trade() -> None:
    """Test rule engine trade decision."""
    engine = RuleEngine()

    engine.add_rule("rule1", lambda x: True)
    engine.add_rule("rule2", lambda x: True)

    should_trade, failed = engine.should_trade({})

    assert should_trade is True
    assert len(failed) == 0
