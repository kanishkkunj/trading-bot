# TradeCraft Autonomous Evolution System

## Overview

The TradeCraft trading bot now includes **autonomous model evolution** — the system continuously learns and improves its strategy based on real trading outcomes.

## How It Works

### 1. **Continuous Learning Loop**

```
Trade Execution
    ↓
Data Collection (SQLite)
    ↓
Every 50 trades / Every 2 hours
    ↓
Check Evolution Trigger
    ↓
If triggered:
  • Fetch all trades from database
  • Retrain RandomForest on real outcomes
  • Calculate performance metrics
  • Adapt entry/exit logic
  • Save improved model (new version)
  • Log evolution event
```

### 2. **What Gets Recomputed Each Evolution**

#### A. **Feature Importance Updates**
The model recalculates which indicators matter most based on recent performance:
- **ATR** (volatility) — how important is risk management?
- **RSI** (momentum) — how overbought/oversold conditions
- **Volume_Ratio** — confirmation signals
- **Price_Momentum** — trend direction
- **SMA_Distance** — distance from moving average

#### B. **Strategy Adaptation**
Based on recent 20-trade performance:

| Condition | Action |
|-----------|--------|
| Win rate > 60% | ✅ Increase entry frequency (be bullish) |
| Win rate < 45% | 🛑 Reduce entry frequency (be cautious) |
| Recent P&L negative | 🛑 Tighten stop losses (protect capital) |
| Recent P&L positive | 📈 Increase position sizes (scale wins) |

#### C. **Model Improvement**
- **More training data** = Better generalization (learns market patterns)
- **Recursive feedback** = Learns which trades are profitable
- **Version control** = Track what changed, revert if needed

### 3. **Evolution Events Logged**

Every evolution creates a record:
```json
{
  "timestamp": "2026-02-18T15:30:00",
  "version": 2,
  "metrics": {
    "total_trades": 50,
    "win_rate": 56.0,
    "total_pnl": 2840,
    "avg_pnl_per_trade": 56.8,
    "recent_20_win_rate": 65.0,
    "recent_20_pnl": 1240
  },
  "strategy_adjustments": {
    "entry_threshold": 0.6,
    "position_size": 1.2,
    "stop_loss_multiplier": 1.0
  }
}
```

### 4. **When Evolution Happens**

**Triggers:**
- ✅ Every 50 closed trades (primary trigger)
- ✅ Every 2 hours (backup trigger)
- ✅ Off-market hours (daily check)

**Example Timeline:**
```
9:15 AM  → Market opens, trading starts
2:50 PM  → Market closes after ~50 trades
3:00 PM  → Evolution Check #1 (off-market)
          → If 50+ trades: Retrain model v1 → v2
5:00 PM  → Evolution Check #2 (2-hour backup)
          → If improved: Update model
Next Day → Repeat with evolved v2 model
```

## What You'll See

### Terminal Logs
```
2026-02-18 15:30:00 [EVOLUTION] 🔄 Checking for autonomous model evolution...
2026-02-18 15:30:00 [EVOLUTION] 🤖 Training improved model on 50 trades...
2026-02-18 15:30:00 [EVOLUTION] ✅ New model accuracy: 75.23%
2026-02-18 15:30:00 [EVOLUTION] 📊 Updated feature importance:
2026-02-18 15:30:00 [EVOLUTION]    ATR                 : 0.3210
2026-02-18 15:30:00 [EVOLUTION]    RSI                 : 0.2140
2026-02-18 15:30:00 [EVOLUTION]    ...
2026-02-18 15:30:00 [EVOLUTION] 🔄 Adapting strategy based on performance...
2026-02-18 15:30:00 [EVOLUTION]    📈 Recent performance strong - increasing entry frequency
2026-02-18 15:30:00 [EVOLUTION] ✅ EVOLUTION COMPLETE: Model v2
```

### API Endpoint
```
GET http://localhost:5000/api/evolution
```

Response:
```json
{
  "current_version": {
    "version": 2,
    "trained_on_trades": 50,
    "last_trained": "2026-02-18T15:30:00",
    "accuracy": 0.7523
  },
  "recent_events": [
    {
      "timestamp": "2026-02-18T15:30:00",
      "version": 2,
      "metrics": { ... }
    }
  ]
}
```

## Files Generated

```
data/
├── signal_model.pkl          (Latest trained model)
├── scaler.pkl                (Feature scaler)
├── model_history.json        (Current version info)
└── evolution_log.jsonl       (All evolution events)
```

## How This Makes You Money

1. **Day 1-2:** Model trained on historical data (1042 trades)
2. **Day 3:** Model evolves based on live market data
3. **Day 4+:** Strategy continuously adapts to market regime
4. **Week 1:** Model has seen 100+ real trades, confidence increases
5. **Month 1:** Model is fine-tuned to CURRENT market patterns

**Result:** ✅ Strategy that gets **smarter every day**, not stale

## Safety Mechanisms

- ✅ New model must improve accuracy (else keep old)
- ✅ Changes are logged (full audit trail)
- ✅ Can revert to previous version if needed
- ✅ Strategy adjustments are constrained (no crazy changes)
- ✅ Position sizes capped at max 1.2x during good runs

## Monitoring Evolution

**Check bot status:**
```bash
curl http://localhost:5000/api/evolution
```

**Expected output over time:**
```
Day 1: version 0 (pre-trained on backtest)
Day 1 (5 PM): version 1 (evolved on 50 live trades)
Day 2 (3 PM): version 2 (evolved on 100 live trades)
Day 3 (3 PM): version 3 (evolved on 150 live trades)
...
```

Each version is **smarter than the last** because it learns from real market outcomes.

---

**TL;DR:** Your bot learns and improves every day. The longer it trades, the better it gets.
