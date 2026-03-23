"""
trading_loop.py
Main trading loop chaining all modules: fetch data → run features → ML predict → Claude validate → risk check → execute → log → alert
"""
import time
import logging
from app.data.fetcher import fetch_market_data
from app.engine.features import extract_features
from app.engine.model import MLModel
from app.strategy import ClaudeDecisionService, SignalScorer
from app.llm_reasoning import ClaudeReasoner
from app.risk.policy import risk_check
from app.execution import execute_trade
from app.alerts import email, telegram, whatsapp

logger = logging.getLogger("trading_loop")

class TradingLoop:
    def __init__(self):
        self.ml_model = MLModel()
        self.signal_scorer = SignalScorer()
        self.claude = ClaudeReasoner()
        self.claude_service = ClaudeDecisionService(self.ml_model, self.signal_scorer, self.claude)

    def run_once(self):
        # 1. Fetch data
        market_data = fetch_market_data()
        # 2. Run features
        features = extract_features(market_data)
        # 3. ML predict
        technical_signals = self._get_technical_signals(market_data)
        # 4. Claude validate
        decision = self.claude_service.decide_trade(features, technical_signals)
        # 5. Risk check
        if not risk_check(decision):
            logger.info("Trade blocked by risk policy", extra=decision)
            self._send_alert("Trade blocked by risk policy", decision)
            return
        # 6. Execute
        result = execute_trade(decision)
        # 7. Log
        logger.info("Trade executed", extra=result)
        # 8. Alert
        self._send_alert("Trade executed", result)

    def _get_technical_signals(self, market_data):
        # Placeholder: extract technical signals from market data
        return {
            "liquidity": market_data.get("liquidity", 1.0),
            "recent_accuracy": 0.5,
            "macro": 0.5
        }

    def _send_alert(self, subject, content):
        email.send(subject, content)
        telegram.send(subject, content)
        whatsapp.send(subject, content)

    def run_forever(self, interval=60):
        while True:
            self.run_once()
            time.sleep(interval)
