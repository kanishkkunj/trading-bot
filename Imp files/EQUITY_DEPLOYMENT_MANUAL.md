# EQUITY DEPLOYMENT MANUAL
## Strategy: NIFTY50 Index Stocks with Rs 500 Capital

### Configuration
**Entry Rules:**
- Ensemble Signal Threshold: 0.5
- RSI(14) Threshold: < 45
- SMA Filter: Above SMA(50)
- Volume Confirmation: False

**Exit Rules:**
- Stop Loss: 1.0  ATR(14)
- Profit Target: 2.5  ATR(14)
- Hold Period: 2 days
- Time Stop: None days if no profit

### Performance (Backtest)
- Sharpe Ratio: 0.00
- Profit Factor: 0.00
- Win Rate: 0.0%
- Max Drawdown: 0.0%
- Total Trades (26 years): 0

### Capital Structure
- Initial Capital: Rs 500
- Leverage: 1.0 (No leverage initially)
- Position Size: 1 share (or fractional) per signal
- Max Open Positions: 2 concurrent
- Upscale: To Rs 1,000 if first 50 trades show >50% win rate

### Risk Management
- Risk Per Trade: 1% of capital = Rs 5
- Max Daily Loss: None (too small to matter)
- Brokerage: 0.03% per trade (equity, not futures)
- Slippage: Minimal (equity markets more liquid)

### Deployment Checklist
- [ ] Choose broker (Zerodha/Angel/ICICI Direct/etc)
- [ ] Set up demat account
- [ ] Transfer initial capital: Rs 500
- [ ] Verify market data feeds
- [ ] Test entry/exit logic on 1 share trades
- [ ] Monitor first 20 trades manually
- [ ] Scale to Rs 1,000 after 50 trades if profitable

### Real Money Deployment Timeline
1. **Week 1**: Deploy with Rs 500
2. **Week 4**: Review first 50 trades
3. **Month 2**: If profitable, increase to Rs 1,000
4. **Month 3**: If >20% return, increase to Rs 2,500
5. **Month 6**: If cumulative return >50%, increase to Rs 5,000

### Monthly Review
- Compare equity paper trading performance to live performance
- If metrics diverge >15%, investigate causes
- Retrain model monthly with fresh data
- Review entry/exit signal distribution

### Scaling Path to Futures
Once equity account reaches Rs 20,000-50,000:
1. Allocate 50% to equity continuation (compounding)
2. Allocate 50% to futures (higher returns)
3. Run both strategies in parallel
4. Target combined monthly return: 2-5%

---
Generated: 2026-02-16T15:58:15.786754
