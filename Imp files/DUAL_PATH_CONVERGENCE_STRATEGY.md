# DUAL-PATH CONVERGENCE STRATEGY
## From Equity (Rs 500) -> Futures (Rs 100k+) Scale Path

### PHASE 1: EQUITY FOUNDATION (Weeks 1-4)
**Objective:** Validate strategy in live market with real money

- Deploy Equity strategy with Rs 500
- Execute 50+ trades with real capital
- Monitor for signal quality and fill quality
- Target: 50%+ win rate, >Rs 50 profit

**Go/No-Go Criteria:**
- [OK] Win rate > 50% on first 20 trades -> Continue
- [FAIL] Win rate < 40% -> Retrain model
- [OK] Live performance within 10% of backtest -> Continue
- [FAIL] Live performance diverges >20% -> Review signal logic

**Expected Outcome:**
- Rs 500 -> Rs 550-750 (10-50% return)
- 50+ executed trades
- Validated entry/exit signal quality

### PHASE 2: EQUITY SCALING (Weeks 5-12)
**Objective:** Compound capital while collecting training data

- Scale equity capital to Rs 1,000-2,500
- Continue monitoring live vs. backtest metrics
- Retrain model weekly with fresh market data
- Accumulate trade data for regime analysis

**Expected Growth:**
- Rs 500 -> Rs 1,000 (100% return, target: 4-6 weeks)
- Rs 1,000 -> Rs 2,500 (150% return, target: 8-10 weeks)

**Parallel Activity:**
- Prepare futures infrastructure (broker setup, APIs)
- Validate historical stress tests
- Confirm futures signal generation

### PHASE 3: FUTURES VALIDATION (Weeks 12-16)
**Objective:** Deploy futures strategy in paper trading first

- Run futures strategy on paper trading account
- Execute 100+ simulated trades with Rs 100k capital
- Compare live futures data against backtests
- Validate execution logic and position sizing

**Validation Criteria:**
- Paper trading Sharpe  1.0 ( 80% of backtest)
- Paper trading win rate  40% ( 89% of backtest)
- No major divergence in crisis scenarios

### PHASE 4: DUAL-PATH EXECUTION (Month 4+)
**Objective:** Run both strategies in parallel

**Capital Allocation:**
- Equity: Rs 2,500-5,000 (compounding track)
- Futures: Rs 50,000-100,000 (new capital or migrated equity)

**Expected Monthly Returns:**
- Equity: 2-3% monthly (higher win rate, smaller position)
- Futures: 2-5% monthly (larger position, higher leverage)
- Combined: 4-8% monthly

**Metrics to Track:**
- Correlation between equity and futures returns (should be <0.5)
- Equity account growth rate
- Futures account growth rate
- Combined account volatility
- Combined Sharpe ratio

### CONVERGENCE TRIGGERS

**Trigger 1: Capital Accumulation to Rs 20k**
- Equity account: Rs 5,000-10,000
- Available capital: Rs 10,000-15,000
- Action: Deploy Rs 50,000 to futures (use margin from broker)

**Trigger 2: Consistent Equity Profitability (3+ months)**
- Equity: 50%+ win rate, 1.5+ profit factor
- Equity: Validated across 2+ major crises
- Action: Increase futures capital to Rs 100,000+

**Trigger 3: Futures Validation Success**
- Futures paper trading: 1.0+ Sharpe ratio
- Futures: 40%+ win rate on paper trading
- Futures: Survives all 5 crisis backtests
- Action: Deploy real capital to futures

**Trigger 4: Equity Account at Rs 50k**
- Equity: Accumulated Rs 50,000 through compounding
- Futures: Already established and profitable
- Action: Allocate Rs 25,000 to second futures contract

### LONG-TERM VISION (6-12 Months)
```
Capital Structure Target:
[*] Equity Portfolio: Rs 50,000-100,000 (2-3% monthly return)
[*] Futures Portfolio: Rs 100,000-500,000 (2-5% monthly return)
[*] Combined Capital: Rs 150,000-600,000
   [*] Target Monthly Income: Rs 3,000-30,000
   [*] Annual Target: Rs 36,000-360,000
```

### RISK MANAGEMENT THROUGHOUT

**Monthly Rebalancing:**
- If equity down >10% in a month -> Increase stop losses
- If futures down >15% in a month -> Reduce position size
- If both down >5% -> Increase time filters

**Quarterly Reviews:**
- Retrain both models on latest 2 years of data
- Update ATR parameters based on new volatility regime
- Verify signal generation quality

**Annual Strategy Reset:**
- Full backtesting with 3 years of new data
- Optimize all parameters for current market regime
- Consider new technical indicators if performance diverges

---
Generated: 2026-02-16T15:58:15.787755

## Configuration Parameters Used
### Futures (Rs 100,000):
{
  "ensemble_threshold": 0.55,
  "rsi_threshold": 45,
  "sma_filter": 100,
  "volume_confirm": true
}
{
  "sl_multiplier": 1.5,
  "tp_multiplier": 3.0,
  "hold_period": 5,
  "time_stop": 2
}

### Equity (Rs 500):
{
  "ensemble_threshold": 0.5,
  "rsi_threshold": 45,
  "sma_filter": 50,
  "volume_confirm": false
}
{
  "sl_multiplier": 1.0,
  "tp_multiplier": 2.5,
  "hold_period": 2,
  "time_stop": null
}
