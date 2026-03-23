"""Research utilities: backtesting, walk-forward, overfitting controls, reporting."""

from app.research.event_backtester import EventBacktester, BacktestResult
from app.research.walk_forward import WalkForwardAnalyzer, WalkForwardResult
from app.research.overfitting import CPCVSplitter, deflated_sharpe_ratio, feature_stability
from app.research.reporting import TearsheetReporter
from app.research.strategy_template import StrategyTemplate
from app.research.optimization import OptunaTuner

__all__ = [
    "EventBacktester",
    "BacktestResult",
    "WalkForwardAnalyzer",
    "WalkForwardResult",
    "CPCVSplitter",
    "deflated_sharpe_ratio",
    "feature_stability",
    "TearsheetReporter",
    "StrategyTemplate",
    "OptunaTuner",
]
