import sys
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from app.data.provider_nse import AngelOneDataProvider
import datetime

if __name__ == "__main__":
    symbol = "RELIANCE.NS"  # Change as needed
    interval = "1d"
    days = 30
    to_date = datetime.datetime.utcnow()
    from_date = to_date - datetime.timedelta(days=days)
    provider = AngelOneDataProvider()
    print(f"Fetching {symbol} from AngelOne...")
    result = provider.get_candle_data(symbol, interval, from_date.strftime("%Y-%m-%d %H:%M"), to_date.strftime("%Y-%m-%d %H:%M"))
    print("Raw API response:")
    print(result)