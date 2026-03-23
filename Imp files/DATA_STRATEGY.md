# Data Strategy & Indian Stock Market Guide — TradeCraft

---

## 1. Indian Stock Market Basics

### Trading Hours (IST = UTC+5:30)

| Time | Event | Action |
|------|-------|--------|
| **09:00** | Pre-market opens | Not traded (we ignore) |
| **09:15** | Market opens | **Signal gen starts** |
| **15:30** | Market closes | **Last possible entry** |
| **15:45** | Settlement prep | No trading |
| **16:00** | EOD data published | **Model retraining** |

**Key:** All times in IST. Zerodha API uses this timezone.

---

## 2. Tax & Brokerage Impact (Critical for ₹500–₹1,000 trading)

### Intraday (MIS — Margin Intraday Square-off)

| Cost | Rate | Impact on ₹1,000 account |
|------|------|---|
| **Brokerage** | 0.03% | ₹0.30 round-trip |
| **STT (Equity)** | 0.025% entry + 0.025% exit | ₹0.50 round-trip |
| **Exchange fee** | ~0.01% | ₹0.10 |
| **Total** | ~0.08% | ₹0.90 per round-trip |
| **Break-even move** | 0.08% | Must win by ₹0.80+ |

**Implication:** For ₹500 account, break-even move is ₹0.40. Doable, but tight.

### Options (Intraday)

| Cost | Rate |
|------|------|
| **Brokerage** | 10 per contract (both buy + sell) |
| **STT** | 0.05% on sell side only |
| **Exchange fee** | ₹5 per contract per side |
| **Total** | ~₹25–₹30 per contract round-trip |

**Impact:** On ₹1,000 account trading 1 option = ₹30 cost = 3% overhead. 
**Rule:** Must have 5%+ profit target to justify options trading in micro accounts.

---

## 3. Zerodha API Integration

### Historical Data Fetching

**Problem:** Zerodha API doesn't give 26 years of data directly.  
**Solution:** Hybrid approach.

#### Strategy A: yfinance + NSE API for bootstrap

```python
# Week 1: Download 26 years of NIFTY50 daily data
# Using: yfinance.download('NIFTY-50.NS', start='1998-01-01')
# Or: nsepython library (NSE official Python wrapper)

data_sources = {
    'NIFTY50': 'yfinance (daily, 26 years)',
    'BANKNIFTY': 'yfinance (daily, 26 years)',
    'Individual stocks': 'NSE API / Zerodha historical',
    'Options data': 'Zerodha only (via Kite API)',
}
```

#### Strategy B: Zerodha Kite API (live + recent)

```python
# After bootstrap, use Zerodha for:
# 1. Real-time 1-min candles during market hours
# 2. Recent daily/hourly candles (last 2 years)
# 3. Options data (IV, Greeks, implied volatility)

kite.historical_data(
    instrument_token=token,
    from_date='2024-01-01',  # Recent data
    to_date='2026-02-16',
    interval='minute',  # '1minute', '5minute', '15minute', '60minute', 'day'
)
```

### Rate Limits & Batching

**Zerodha Kite API limits:**
- 120 requests per minute per user
- 1,000 requests per hour

**Strategy:**
- Batch requests in groups of 50 instruments
- Cache aggressively in Redis (quotes, historical data)
- Update every 15 min during market hours (not every tick)

```python
# Batch request example
def fetch_instruments_batch(symbols: List[str], interval: str = '1minute') -> Dict:
    """
    Fetch candles for 50+ instruments efficiently.
    Uses rate-limiting + caching.
    """
    results = {}
    
    for batch in chunks(symbols, 50):  # Batch in groups of 50
        for symbol in batch:
            token = symbol_to_token(symbol)
            candles = kite.historical_data(
                instrument_token=token,
                from_date=today,
                to_date=today,
                interval=interval,
            )
            results[symbol] = candles
            
        time.sleep(1)  # Respect rate limits
        
        # Cache in Redis for 15 minutes
        redis.set(f'candles:{symbol}', json.dumps(candles), ex=900)
    
    return results
```

---

## 4. Database Schema (TimescaleDB)

### Why TimescaleDB?

- **OLAP optimized:** Fast aggregations over time
- **Hyper-table:** Automatically shards time-series data
- **Compression:** 26 years of 1-min data = ~10GB uncompressed → ~2GB compressed
- **Full PostgreSQL:** Can run complex joins + ML queries

### Tables

#### 1. Candles (OHLCV data)

```sql
CREATE TABLE candles (
    time TIMESTAMPTZ NOT NULL,
    instrument_id INT NOT NULL,
    interval VARCHAR(10) NOT NULL,  -- '1minute', '5minute', 'day'
    
    open DECIMAL(10, 2),
    high DECIMAL(10, 2),
    low DECIMAL(10, 2),
    close DECIMAL(10, 2),
    volume BIGINT,
    
    -- Computed fields (cache)
    rsi_14 DECIMAL(10, 4),
    macd DECIMAL(10, 4),
    bb_upper DECIMAL(10, 2),
    bb_lower DECIMAL(10, 2),
    
    PRIMARY KEY (time, instrument_id, interval)
);

SELECT create_hypertable('candles', 'time', if_not_exists => TRUE);
CREATE INDEX idx_candles_instrument ON candles (instrument_id, time DESC);
```

#### 2. Options Data

```sql
CREATE TABLE options_data (
    time TIMESTAMPTZ NOT NULL,
    underlying_id INT,
    strike_price DECIMAL(10, 2),
    expiration_date DATE,
    option_type VARCHAR(2),  -- 'CE', 'PE'
    
    last_price DECIMAL(10, 2),
    bid DECIMAL(10, 2),
    ask DECIMAL(10, 2),
    bid_qty INT,
    ask_qty INT,
    
    -- Greeks
    delta DECIMAL(5, 4),
    gamma DECIMAL(7, 5),
    theta DECIMAL(7, 4),
    vega DECIMAL(7, 4),
    iv_rank DECIMAL(5, 4),
    
    PRIMARY KEY (time, underlying_id, strike_price, option_type, expiration_date)
);

SELECT create_hypertable('options_data', 'time', if_not_exists => TRUE);
```

#### 3. Trades (Audit log)

```sql
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    user_id INT NOT NULL,
    instrument_id INT NOT NULL,
    strategy_type VARCHAR(50),  -- 'equity_momentum', 'options_ic'
    
    side VARCHAR(4),  -- 'BUY', 'SELL'
    quantity INT,
    entry_price DECIMAL(10, 2),
    exit_price DECIMAL(10, 2),
    
    entry_signal_confidence DECIMAL(3, 2),  -- 0.00-1.00
    
    realized_pnl DECIMAL(15, 2),
    realized_pnl_pct DECIMAL(6, 2),
    
    -- Constraints checked
    daily_loss_pct_before DECIMAL(6, 2),
    max_loss_breach BOOLEAN,
    position_limit_breach BOOLEAN,
    
    -- Audit
    feature_snapshot JSONB,  -- Feature values at signal time
    reviewed BOOLEAN DEFAULT FALSE,
    review_notes TEXT,
    
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (instrument_id) REFERENCES instruments(id)
);

CREATE INDEX idx_trades_user_created ON trades (user_id, created_at DESC);
```

#### 4. Model Versioning

```sql
CREATE TABLE model_versions (
    id INT PRIMARY KEY,
    strategy_type VARCHAR(50),  -- 'equity_momentum', 'options_iv'
    
    version_hash VARCHAR(64),  -- Git commit hash
    trained_at TIMESTAMPTZ,
    
    -- Backtest metrics
    backtest_sharpe DECIMAL(5, 2),
    backtest_max_dd DECIMAL(6, 2),
    backtest_win_rate DECIMAL(5, 2),
    
    -- Paper trading metrics (rolling)
    paper_sharpe DECIMAL(5, 2),
    paper_trades_count INT,
    paper_win_rate DECIMAL(5, 2),
    
    -- Status
    is_active BOOLEAN DEFAULT FALSE,
    paused_reason VARCHAR(255),
    
    -- Artifacts
    model_file_path VARCHAR(255),  -- S3 or local
    feature_names JSONB,
    hyperparameters JSONB,
    
    FOREIGN KEY (id) REFERENCES strategies(id)
);
```

---

## 5. Data Flow Architecture

### Daily ETL (End-of-Day)

```
16:00 IST: Market closes
    ↓
16:05: Zerodha publishes EOD data
    ↓
[Data Fetch]
    - Fetch OHLCV for all 50 symbols (NIFTY50)
    - Fetch options Greeks for NIFTY, BANKNIFTY
    - Batch requests (50 at a time)
    ↓
[Data Validation]
    - Check for NaN, gaps, outliers
    - Compare with previous day
    - Flag any anomalies
    ↓
[Compute Features]
    - RSI(14), MACD, Bollinger, VWAP, returns, volatility
    - Takes ~5 minutes for 50 stocks
    ↓
[Store in TimescaleDB]
    - Upsert candles table
    - Update features cache
    ↓
[Model Retraining]
    - Walk-forward validation (last 1 month holdout)
    - XGBoost + LightGBM both trained
    - Compare Sharpe ratios
    - Select best model
    ↓
[Metrics Evaluation]
    - Check model health (Sharpe, max DD, win rate)
    - Compare to backtest baseline
    - Alert if degradation detected
    ↓
[Report Generation]
    - Daily summary sent via WhatsApp/Telegram
    - Latest model metrics + trades from today
    - Alert if pause needed
```

**Total time:** ~20 minutes (mostly feature engineering + retraining)
**Frequency:** Daily after 16:00 IST

### Intraday Signal Generation (Every 15 min)

```
09:15, 09:30, 09:45, ... 15:15 (market hours)
    ↓
[Fetch Live Data]
    - Get last 1-min candles for all symbols
    - Check options IV rank
    - Single batch request (rate-limit friendly)
    ↓
[Compute Signals]
    - Apply trained ML model to latest features
    - Get probability + confidence scores
    - Apply rule filters (trend, volume, time-of-day)
    ↓
[Generate Orders]
    - Equity strategy: Check momentum signals
    - Options strategy: Check IV + direction
    - Risk manager validates position sizing
    ↓
[Execute / Alert]
    - Paper broker: Place orders
    - Dashboard: Update live signals
    - Alert if high-conviction trade generated
```

**Latency target:** < 30 seconds from data fetch to order placement

---

## 6. Zerodha Account Setup Checklist

When you're ready to go live:

- [ ] Zerodha account created + verified
- [ ] Kite API enabled (under Settings → API)
- [ ] API key + secret obtained
- [ ] Test API connection (health check)
- [ ] Sample order placed in paper mode
- [ ] Position reconciliation verified
- [ ] Margin available checked (should show available margin)
- [ ] GTT (Good Till Triggered) orders tested (optional)
- [ ] Market depth + Level 1 data accessible

**Do NOT proceed to live trading without all checks ✅**

---

## 7. Data Quality Checklist

Every imported candle must pass:

- [ ] No NaN or infinite values
- [ ] High >= Low >= Close >= Open (HLCO rule relaxed for gaps)
- [ ] Volume > 0
- [ ] Timestamp is unique per instrument per interval
- [ ] No future timestamps
- [ ] Price within 10% of previous close (outlier detection)
- [ ] No duplicate candles
- [ ] Gap-free (consecutive timestamps)

**If any check fails:** Log, quarantine, alert human.

---

## 8. Feature Drift Monitoring

**Problem:** Markets change. Features that worked in 2023 might fail in 2025.

### Monitoring Strategy

```python
def monitor_feature_drift(current_period, baseline_period):
    """
    Check if feature distributions have shifted significantly.
    Uses Kolmogorov-Smirnov test.
    """
    for feature in feature_list:
        current = current_period[feature]
        baseline = baseline_period[feature]
        
        ks_stat, p_value = scipy.stats.ks_2samp(current, baseline)
        
        if p_value < 0.05:  # Significant shift
            alert(f"Feature drift detected: {feature}, ks={ks_stat:.3f}")
```

**Action:** If drift detected → reduce position size, schedule retraining

---

## 9. Realistic Data Assumptions

### Historical data (26 years for backtesting)

- **Source:** yfinance (free, daily OHLCV for NIFTY50)
- **Coverage:** 1998–2026
- **Granularity:** Daily close (for backtesting)
- **Gaps:** Weekends + holidays handled automatically

### Live data (Zerodha)

- **Latency:** 1-2 seconds delay (normal)
- **Availability:** 09:15–15:30 IST
- **Accuracy:** Real-time, live prices from NSE
- **Caching:** 15-minute cache for non-critical data

---

## 10. Cost Optimization

### Data transfer costs

- Zerodha API: **Free** (included with brokerage)
- yfinance: **Free** (public API)
- AWS S3 (for model artifacts): ~$1/month
- PostgreSQL (self-hosted): **Free**

### Bandwidth optimization

- Batch requests: 50 symbols per API call
- Cache aggressively: 15-minute Redis cache
- Compress time-series: Use TimescaleDB compression
- No per-second data: Use 1-min candles (not ticks)

**Total data infra cost: ~$0** (can run entirely locally)

---

## 11. Timeline: Data Integration

| Phase | Task | Effort | Timeline |
|-------|------|--------|----------|
| **Phase 1a** | Bootstrap: Download 26 years NIFTY50 via yfinance | 2h | Day 1 |
| **Phase 1b** | Zerodha auth + Kite API connection test | 2h | Day 2 |
| **Phase 1c** | Database schema + TimescaleDB setup | 3h | Day 2 |
| **Phase 1d** | Data ingestion pipeline + validation | 4h | Day 3 |
| **Phase 1e** | Redis caching layer | 2h | Day 3 |
| **Phase 2** | Options data ingestion (Greeks, IV) | 4h | Week 2 |
| **Phase 3** | Daily EOD ETL + retraining pipeline | 6h | Week 2–3 |
| **Phase 4** | Intraday signal generation (every 15 min) | 4h | Week 3 |

---

## Data Integrity Guarantees

✅ No lookahead bias (features only use past data)  
✅ No microstucture bias (use only candle closes, not intra-candle)  
✅ No survivorship bias (include delisted stocks if backtesting equity indices)  
✅ Realistic costs (0.08% equity round-trip, ₹30/option)  
✅ Slippage modeled (market impact on fills)  
✅ Audit logging (every feature computed, every trade logged)

---

**Ready to start data integration in Phase 1?**
