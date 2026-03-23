# FUTURES DEPLOYMENT MANUAL
## Strategy: NIFTY50 Futures with Rs 100,000 Capital

### Configuration
**Entry Rules:**
- Ensemble Signal Threshold: 0.55
- RSI(14) Threshold: < 45
- SMA Filter: Above SMA(100)
- Volume Confirmation: True

**Exit Rules:**
- Stop Loss: 1.5  ATR(14)
- Profit Target: 3.0  ATR(14)
- Hold Period: 5 days
- Time Stop: 2 days if no profit

### Performance (Backtest)
- Sharpe Ratio: 0.00
- Profit Factor: 0.00
- Win Rate: 0.0%
- Max Drawdown: 0.0%
- Total Trades (26 years): 0

### Capital Structure
- Initial Capital: Rs 100,000
- Leverage: 1.0 (No leverage, conservative)
- Lot Size: 75 units per contract (NIFTY50 standard)
- Position Size: 1 contract per signal
- Max Open Positions: 3 concurrent

### Risk Management
- Risk Per Trade: 1% of capital = Rs 1,000
- Max Daily Loss: -5% = Rs 5,000 (KILL SWITCH)
- Stop Loss Maximum: Rs 2,000 (2% of capital)
- Target Profit: Rs 6,000 (6% of capital)

### Fee & Slippage Assumptions
- Brokerage: 0.16% per round trip
- Slippage: 0.10% average

### Deployment Checklist
- [ ] Verify live data feed connection (NSE)
- [ ] Configure order management system
- [ ] Set up risk limits in trading platform
- [ ] Enable daily loss kill switch (-5%)
- [ ] Test on 1 mini-contract first
- [ ] Monitor first 50 trades manually
- [ ] Scale to full capital after validation

### Monthly Review
- Check strategy metrics against backtest
- Review win rate, profit factor, Sharpe ratio
- Retrain model if performance degrades >20%
- Update stop loss and profit target levels based on volatility

### Scaling Path
1. **Month 1**: Rs 100,000 with 1 contract
2. **Month 3**: Scale to 2 contracts if returns >10%
3. **Month 6**: Scale to 3 contracts if consistent
4. **Month 12**: Consider scaling to Rs 500,000+ if validated

---
Generated: 2026-02-16T15:58:15.786754
