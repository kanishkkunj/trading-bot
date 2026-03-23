## Claude Backtest Guide

### What It Does
Simulates your trading system on **historical NIFTY data** (last month, 15-min candles) to show:
- All BUY/SELL decisions Claude would make
- Simulated entry/exit prices
- Total P&L (profit/loss) in INR
- Win rate, average wins/losses, max loss
- Final capital

### How to Run

#### Option 1: With Claude API (Real Decisions)
```bash
# Set your OpenRouter API key
$env:OPENROUTER_API_KEY = "sk-or-XXXXX..."

# Run backtest
python scripts/backtest_simple.py
```

#### Option 2: Demo Mode (No API Key)
```bash
# Run without API key (uses mock decisions)
python scripts/backtest_simple.py
```

### Customization

Edit the **configuration** at top of script:
```python
STARTING_CAPITAL = 100_000        # Starting money (INR)
MAX_CAPITAL_PER_TRADE = 30_000    # Max per trade
MAX_DAILY_LOSS = 2_000            # Max loss per day
DAYS_BACKTEST = 30                # How far back to test
CONFIDENCE_THRESHOLD = 6          # Claude confidence >= 6 to trade
```

### Output Example
```
======================================================================
CLAUDE BACKTEST - Historical NIFTY Data
======================================================================
Period: Last 30 days | Candle: 15-min
Start Capital: INR 100,000
Max Per Trade: INR 30,000
======================================================================

[BUY]  14:30 | 1 @ 23500 | Cost: 23,500 | Conf: 8/10
[SELL] 14:45 | 1 @ 23650 | Entry: 23500 | P&L: 150 | Conf: 7/10
[BUY]  15:00 | 1 @ 23600 | Cost: 23,600 | Conf: 7/10
...

======================================================================
BACKTEST RESULTS
======================================================================

Financial:
  Start Capital:  INR      100,000
  Total P&L:      INR        1,235
  Return:                  1.24%
  Final Capital:  INR      101,235

Trades:
  Total Actions:             12
  Closed Trades:              6
  Wins:                       4
  Losses:                     2
  Win Rate:              66.67%
  Avg Win:        INR          487
  Avg Loss:       INR         -126

======================================================================
```

### What the Columns Mean

**Trade Log:**
- **[BUY]** or **[SELL]**: Action taken
- **Time**: When the trade was executed (IST)
- **Qty @ Price**: Quantity × Entry price
- **Cost**: Total capital used (for BUY) or Proceeds (for SELL)
- **Entry**: Previous entry price (for SELL exit)
- **P&L**: Profit/Loss in INR
- **Conf**: Claude's confidence (1-10 scale)

**Results:**
- **Start Capital**: Money at beginning
- **Total P&L**: Total profit/loss across all trades
- **Return**: Percentage gain/loss
- **Final Capital**: Money at end

- **Closed Trades**: Trades with both entry AND exit
- **Wins**: Trades that made money
- **Losses**: Trades that lost money
- **Win Rate**: % of trades that were profitable

### Key Parameters

| Parameter | Current | Description |
|-----------|---------|-------------|
| STARTING_CAPITAL | 100,000 | How much money to simulate with |
| MAX_CAPITAL_PER_TRADE | 30,000 | Max position size per trade |
| MAX_DAILY_LOSS | 2,000 | Stop trading if daily loss > this |
| CONFIDENCE_THRESHOLD | 6 | Only trade if Claude confidence >= this |
| DAYS_BACKTEST | 30 | How many days of historical data |
| CANDLE_INTERVAL | 15m | Use 15-minute candles |

### How It Works

1. **Fetch Data**: Downloads last 30 days of NIFTY 15-min candles from Yahoo Finance
2. **Compute Indicators**: EMA9, EMA21, RSI
3. **Every ~75 mins**: Calls Claude with current price + indicators
4. **Claude Decides**: Returns BUY/SELL/HOLD with confidence
5. **Simulate Trade**: If confidence >= 6, execute the trade at current price
6. **Track P&L**: When position closes (SELL), calculate profit/loss
7. **Report**: Show summary and all trades

### Important Notes

- **Demo Mode** (no API key): Uses mock response `{"action": "HOLD", "confidence": 5}` → no trades execute
- **Live Mode** (with API key): Calls Claude for each decision point
- **Slippage**: Assumes perfect execution at current price (no slippage/fees)
- **Position**: Simulates only 1 open position at a time (NIFTY)
- **Data**: Uses Yahoo Finance historical data (1min delay)

### Time Frame

- E.g., `days=30` = last 30 calendar days of market data
- 15-min candles = ~100 candles per trading day
- ~2,500 candles per 30 days
- Every 5th candle = ~500 decision points

### Running with Your Real API Key

```bash
# PowerShell
$env:OPENROUTER_API_KEY = "sk-or-xxxxxxxxxxxx"
python scripts/backtest_simple.py

# Or from terminal directly
Set-Item -Path Env:OPENROUTER_API_KEY -Value "sk-or-xxxxxxxxxxxx"
python scripts/backtest_simple.py
```

**Find your API key** at https://openrouter.ai/keys

### Next Steps

1. **Run demo** to see it works
2. **Set API key** and run live backtest
3. **Adjust parameters** (capital, dates, symbols)
4. **Compare results** with your live system
5. **Fine-tune prompt** based on backtest P&L
