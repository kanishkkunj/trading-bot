"""Yahoo Finance data provider."""


from datetime import datetime
from typing import Optional
import yfinance as yf
import pandas as pd

# Symbol mapping for Yahoo Finance
def map_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if symbol == "NIFTY":
        return "^NSEI"
    elif symbol == "BANKNIFTY":
        return "^NSEBANK"
    elif symbol.endswith(".NS"):
        return symbol
    elif symbol.isalpha():
        return f"{symbol}.NS"
    return symbol

class YFinanceProvider:
    """Yahoo Finance data provider."""

    def __init__(self):
        pass

    def get_quote(self, symbol: str) -> Optional[dict]:
        """Get live quote from Yahoo Finance."""
        try:
            yf_symbol = map_symbol(symbol)
            ticker = yf.Ticker(yf_symbol)
            fast_info = getattr(ticker, "fast_info", {})
            last_price = fast_info.get("last_price")
            # Fallback to regularMarketPrice if fast_info is missing
            info = getattr(ticker, "info", {})
            reg_price = info.get("regularMarketPrice")
            price = last_price if last_price not in [None, 0] else reg_price
            if price in [None, 0]:
                return None
            return {
                "symbol": symbol,
                "last_price": price,
                "change": fast_info.get("change", info.get("regularMarketChange")),
                "change_percent": fast_info.get("change_percent", info.get("regularMarketChangePercent")),
                "volume": fast_info.get("volume", info.get("regularMarketVolume")),
                "timestamp": datetime.utcnow(),
            }
        except Exception as e:
            print(f"Error fetching quote: {e}")
            return None

    def get_historical_data(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Get historical data from Yahoo Finance."""
        try:
            yf_symbol = map_symbol(symbol)
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period=period, interval=interval)
            return df
        except Exception as e:
            print(f"Error fetching historical data: {e}")
            return pd.DataFrame()

    def get_ohlcv(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Get OHLCV data for a date range."""
        try:
            yf_symbol = map_symbol(symbol)
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(start=start, end=end, interval=interval)
            return df
        except Exception as e:
            print(f"Error fetching OHLCV data: {e}")
            return pd.DataFrame()
