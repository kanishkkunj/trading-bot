"""
claude_layer.py
Integrates Claude AI reasoning with ML and technical signals.
"""
from app.engine.model import MLModel
from app.strategy.signal_scorer import SignalScorer, SignalContext
from app.llm_reasoning import ClaudeReasoner

class ClaudeDecisionService:
    def __init__(self, ml_model: MLModel, signal_scorer: SignalScorer, claude: ClaudeReasoner):
        self.ml_model = ml_model
        self.signal_scorer = signal_scorer
        self.claude = claude

    def decide_trade(self, features: dict, technical_signals: dict) -> dict:
        # Get ML prediction and confidence
        X = self._features_to_df(features)
        ml_pred = self.ml_model.predict(X)[0]
        ml_conf = self.ml_model.predict_proba(X)[0][1]
        # Score signal
        signal_ctx = SignalContext(
            model_confidence=ml_conf,
            uncertainty=1-ml_conf,
            liquidity_score=technical_signals.get('liquidity', 1.0),
            recent_accuracy=technical_signals.get('recent_accuracy', 0.5),
            macro_alignment=technical_signals.get('macro', 0.5),
            features=features
        )
        signal_score = self.signal_scorer.score(signal_ctx)
        # Aggregate for Claude
        ml_outputs = {
            'prediction': ml_pred,
            'confidence': ml_conf,
            'signal_score': signal_score
        }
        # Call Claude for reasoning
        result = self.claude.reason(ml_outputs, technical_signals)
        return result

    def _features_to_df(self, features: dict):
        import pandas as pd
        return pd.DataFrame([features])
