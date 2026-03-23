# LLM Reasoning Layer (Claude as Brain)

This file explains how a Large Language Model (LLM) like Claude can be integrated as a reasoning layer in the Tradecraft application.

## Purpose
- Acts as the "brain" that reviews ML model predictions and technical signals.
- Decides confidence level before placing a trade.
- Explains every decision in plain English.

## How It Works
1. **Input Aggregation**
   - Collects predictions from ML models (market direction, volatility, risk).
   - Gathers technical signals (momentum, mean reversion, options analytics).
2. **Reasoning & Decision**
   - Claude reviews all inputs, weighs evidence, and determines confidence level for each trade.
   - Can override or confirm ML/technical signals based on context and historical performance.
3. **Trade Execution**
   - Only places trades when confidence is high, or provides rationale for abstaining.
4. **Explanation**
   - Generates plain English explanations for every decision, including:
     - Why a trade is placed or skipped
     - Which signals were most influential
     - Risk factors considered
     - Expected outcome

## Integration Points
- Sits between ML/strategy modules and broker/execution layer.
- Can be implemented as a service that receives model outputs and returns trade decisions + explanations.

## Benefits
- Adds transparency and interpretability to trading decisions.
- Reduces blind reliance on ML models.
- Provides actionable feedback and rationale to users.

---
See ML models, strategy, and risk docs for supporting logic.