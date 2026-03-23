import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytz
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())
BACKEND_APP = Path(__file__).resolve().parent.parent
if str(BACKEND_APP) not in sys.path:
    sys.path.insert(0, str(BACKEND_APP))

class AngelOneDataProvider:
    def __init__(self):
        import logging
        from SmartApi.smartConnect import SmartConnect
        import pyotp
        self.logger = logging.getLogger("AngelOneDataProvider")
        self.logger.setLevel(logging.INFO)
        if not self.logger.hasHandlers():
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.api_key = os.getenv('ANGELONE_API_KEY')
        if not self.api_key:
            self.logger.error('ANGELONE_API_KEY is missing or not loaded!')
            raise RuntimeError('ANGELONE_API_KEY is missing. Cannot initialize AngelOneDataProvider.')
        self.client_code = os.getenv('ANGELONE_CLIENT_ID')
        self.password = os.getenv('ANGELONE_API_SECRET')
        self.totp_secret = os.getenv('ANGELONE_TOTP_SECRET')
        self.logger.info(f"Loaded API key: {self.api_key}, Client ID: {self.client_code}, Password: {'*' * len(self.password) if self.password else None}, TOTP: {'set' if self.totp_secret else 'missing'}")
        self.api = SmartConnect(api_key=self.api_key)
        # Login logic using TOTP
        try:
            totp = pyotp.TOTP(self.totp_secret).now()
            data = self.api.generateSession(clientCode=self.client_code, password=self.password, totp=totp)
            self.logger.info(f"AngelOne login response: { {k: v for k, v in data.items() if k not in ['password', 'api_key', 'client_code', 'totp', 'jwtToken', 'feedToken', 'jwt_token', 'feed_token']} }")
            if not data.get('status'):
                self.logger.error(f"AngelOne login failed: {data}")
            else:
                self.logger.info("AngelOne login successful.")
                # Extract tokens from the 'data' field
                login_data = data.get('data', {})
                self.jwt_token = login_data.get('jwtToken') or login_data.get('jwt_token')
                self.feed_token = login_data.get('feedToken') or login_data.get('feed_token')
        except Exception as e:
            self.logger.error(f"AngelOne login exception: {e}")

    def get_symbol_token(self, symbol):
        index_token_candidates = {
            # Candidate tokens for indices (try in order until data is returned)
            "NIFTY": ["99926000", "26009", "26000"],
            "BANKNIFTY": ["99926001", "26037", "26001"],
        }
        if symbol.upper() in index_token_candidates:
            return index_token_candidates[symbol.upper()]

        # Use searchScrip to get the numeric token for the symbol
        try:
            mapped_symbol = symbol[:-3] if symbol.endswith('.NS') else symbol
            resp = self.api.searchScrip('NSE', mapped_symbol)
            if resp.get('status') and resp.get('data'):
                # Find the first matching symboltoken
                for item in resp['data']:
                    if item['tradingsymbol'] == mapped_symbol:
                        return item['symboltoken']
                # Fallback: return the first token
                return resp['data'][0]['symboltoken']
            self.logger.error(f"searchScrip failed for {symbol}: {resp}")
        except Exception as e:
            self.logger.error(f"get_symbol_token exception: {e}")
        return None

    def _to_ist_str(self, dt: datetime) -> str:
        tz_ist = pytz.timezone("Asia/Kolkata")
        tz_utc = pytz.utc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz_utc)
        else:
            dt = dt.astimezone(tz_utc)
        return dt.astimezone(tz_ist).strftime('%Y-%m-%d %H:%M')

    def get_candle_data(self, symbol, interval, from_date, to_date):
        # Map Yahoo/standard symbol to AngelOne format (e.g., 'RELIANCE.NS' -> 'RELIANCE')
        def map_symbol(sym):
            if sym.endswith('.NS'):
                return sym[:-3]
            return sym

        interval_map = {
            '1m': 'ONE_MINUTE',
            '3m': 'THREE_MINUTE',
            '5m': 'FIVE_MINUTE',
            '10m': 'TEN_MINUTE',
            '15m': 'FIFTEEN_MINUTE',
            '30m': 'THIRTY_MINUTE',
            '1h': 'ONE_HOUR',
            '1d': 'ONE_DAY',
        }
        mapped_symbol = map_symbol(symbol)
        mapped_interval = interval_map.get(interval, interval)
        token_candidates = self.get_symbol_token(symbol)
        if not token_candidates:
            self.logger.error(f"No symbol token found for symbol: {symbol} (mapped: {mapped_symbol})")
            return None

        if isinstance(token_candidates, str):
            token_candidates = [token_candidates]

        # Convert datetimes to AngelOne-compatible string format: 'YYYY-MM-DD HH:MM'
        from_date_str = self._to_ist_str(from_date)
        to_date_str = self._to_ist_str(to_date)

        for token in token_candidates:
            params = {
                'exchange': 'NSE',
                'symboltoken': token,
                'interval': mapped_interval,
                'fromdate': from_date_str,
                'todate': to_date_str,
            }
            self.logger.info(f"getCandleData params: {params}")
            try:
                data = self.api.getCandleData(params)
                self.logger.info(f"Raw AngelOne getCandleData response: {data}")
                if isinstance(data, dict) and data.get("data"):
                    self.logger.info(f"Using token {token} for {symbol}")
                    return data
            except Exception as e:
                self.logger.error(f"get_candle_data exception for token {token}: {e}")

        self.logger.error(f"All token candidates failed/empty for {symbol}")
        return None

    def stream_live_data(self, symbol):
        """Fetch live quote for a symbol using AngelOne SmartApi WebSocket."""
        from datetime import datetime
        try:
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2
            mapped_symbol = symbol[:-3] if symbol.endswith('.NS') else symbol
            # Use standard AngelOne index tokens when provided
            symbol_token = self.get_symbol_token(symbol)
            if not symbol_token:
                self.logger.error(f"No symbol token found for symbol: {symbol}")
                return {"symbol": symbol, "last_price": 0, "error": "Symbol token not found"}

            # Use jwt_token and feed_token from login
            if not hasattr(self, 'jwt_token') or not hasattr(self, 'feed_token'):
                self.logger.error("JWT token or feed token missing after login.")
                return {"symbol": symbol, "last_price": 0, "error": "JWT/feed token missing"}

            # Log token values for debugging (do not log secrets)
            self.logger.info(f"SmartWebSocketV2 init: jwt_token={'set' if self.jwt_token else 'missing'}, api_key={'set' if self.api_key else 'missing'}, client_code={'set' if self.client_code else 'missing'}, feed_token={'set' if self.feed_token else 'missing'}")

            correlation_id = "tradecraft-quote"
            mode = 1  # 1 for market data
            token_list = [{"exchangeType": 1, "tokens": [str(symbol_token)]}]

            tick_result = {}
            tick_messages = []
            def on_data(wsapp, message):
                tick_messages.append(message)
                self.logger.info(f"WebSocket tick message: {message}")
                # Only close on first valid tick
                if not tick_result and isinstance(message, dict) and message.get("ltp", 0) > 0:
                    tick_result.update(message)
                    wsapp.close()

            def on_open(wsapp):
                wsapp.subscribe(correlation_id, mode, token_list)

            sws = SmartWebSocketV2(self.jwt_token, self.api_key, self.client_code, self.feed_token)
            sws.on_open = on_open
            sws.on_data = on_data
            sws.connect()

            # Wait for tick_result to be filled (simple blocking)
            import time
            timeout = 15  # Increased timeout for tick data
            start = time.time()
            while not tick_result and time.time() - start < timeout:
                time.sleep(0.1)

            if tick_result:
                # Parse tick_result for required fields
                return {
                    "symbol": symbol,
                    "last_price": float(tick_result.get("ltp", 0)),
                    "change": float(tick_result.get("change", 0)),
                    "change_percent": float(tick_result.get("percentChange", 0)),
                    "bid": float(tick_result.get("bestBid", 0)),
                    "ask": float(tick_result.get("bestAsk", 0)),
                    "bid_qty": int(tick_result.get("bestBidQty", 0)),
                    "ask_qty": int(tick_result.get("bestAskQty", 0)),
                    "volume": int(tick_result.get("volume", 0)),
                    "timestamp": tick_result.get("lastTradeTime", datetime.utcnow()),
                }
            else:
                error_msg = (
                    f"No live tick data received for {symbol}. "
                    f"This may be due to an invalid symbol token, unsupported instrument, or account permissions. "
                    f"Messages: {tick_messages}"
                )
                self.logger.error(error_msg)
                return {
                    "symbol": symbol,
                    "last_price": 0,
                    "error": error_msg,
                    "messages": tick_messages
                }
        except Exception as e:
            self.logger.error(f"stream_live_data exception: {e}")
            return {
                "symbol": symbol,
                "last_price": 0,
                "error": str(e),
            }

class DhanPaperTradeProvider:
    def __init__(self):
        from dhanhq import DhanHQ
        self.api_key = os.getenv('DHAN_API_KEY')
        self.client_id = os.getenv('DHAN_CLIENT_ID')
        self.base_url = os.getenv('DHAN_BASE_URL') or 'https://api.dhan.co'
        self.dhan = DhanHQ(self.api_key, self.client_id, base_url=self.base_url)

    def place_order(self, order_params):
        # Use DhanHQ API for paper trading
        try:
            return self.dhan.place_order(order_params)
        except Exception as e:
            return {"error": str(e)}

    # Add other paper trading methods as needed
            def get_alpha_vantage_quote(self, symbol: str, api_key: str = None) -> Optional[dict]:
                """Get NIFTY price from Alpha Vantage."""
                if not api_key:
                    return {"symbol": symbol, "last_price": 0, "error": "Alpha Vantage API key required. Please provide your API key."}
                try:
                    from alpha_vantage.timeseries import TimeSeries
                    ts = TimeSeries(key=api_key, output_format='json')
                    # Alpha Vantage uses 'NSEI' for NIFTY index
                    data, meta = ts.get_quote_endpoint(symbol='NSEI')
                    price = float(data.get('05. price', 0))
                    if price:
                        return {"symbol": symbol, "last_price": price}
                    else:
                        return {"symbol": symbol, "last_price": 0, "error": "No price in Alpha Vantage response"}
                except Exception as e:
                    return {"symbol": symbol, "last_price": 0, "error": f"Alpha Vantage exception: {str(e)}"}
        def get_truedata_live_quote(self, symbol: str) -> Optional[dict]:
            """Get live quote from TrueData using TD_live."""
            try:
                from truedata import TD_live
                td_obj = TD_live("trial535", "kanishk535")
                # TrueData expects symbol in its own format, e.g. 'NIFTY'
                quote = td_obj.get_live_data(symbol)
                price = quote.get("last_price") or quote.get("LastPrice")
                if price:
                    return {"symbol": symbol, "last_price": price}
                else:
                    return {"symbol": symbol, "last_price": 0, "error": "No price in TrueData response"}
            except Exception as e:
                return {"symbol": symbol, "last_price": 0, "error": f"TrueData exception: {str(e)}"}
    def get_truedata_quote(self, symbol: str, username: str = None, password: str = None, api_key: str = None) -> Optional[dict]:
        """Get live quote from TrueData API. Credentials required."""
        import requests
        # TrueData API endpoint (example, update as per docs)
        url = f"https://api.truedata.in/market/quote?symbol={symbol}"
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        # Add other headers or auth as required
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                price = data.get("last_price") or data.get("LastPrice")
                if price:
                    return {"symbol": symbol, "last_price": price}
                else:
                    return {"symbol": symbol, "last_price": 0, "error": "No price in TrueData response"}
            else:
                return {"symbol": symbol, "last_price": 0, "error": f"TrueData error: {response.status_code} {response.text}"}
        except Exception as e:
            return {"symbol": symbol, "last_price": 0, "error": f"TrueData exception: {str(e)}"}
"""NSE data provider (placeholder for future implementation)."""

from typing import Optional

import httpx


class NSEDataProvider:
    """NSE (National Stock Exchange) data provider."""

    BASE_URL = "https://www.nseindia.com"

    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url="https://www.nseindia.com",
        )
        # TrueData credentials
        self.truedata_creds = {
            "username": "trial535",
            "password": "kanishk535",
            # Add 'api_key' here if you have one
        }
        self.alpha_vantage_api_key = "NW19YFYBFE05ON9G"

    async def get_quote(self, symbol: str) -> Optional[dict]:
        """Get live quote from NSE using nsepython."""
        from nsepython import nse_quote_ltp
        # Symbol mapping for NSE
        nse_symbol = None
        if symbol.upper() == "NIFTY":
            nse_symbol = "NIFTY 50"
        elif symbol.upper() == "BANKNIFTY":
            nse_symbol = "NIFTY BANK"
        elif symbol.upper().endswith(".NS"):
            nse_symbol = symbol.upper()[:-3]
        else:
            nse_symbol = symbol.upper()
        # Try TrueData TD_live for real-time quote
        td_result = self.get_truedata_live_quote(nse_symbol)
        if td_result and td_result.get("last_price", 0) > 0:
            return td_result

        # Fallback to Alpha Vantage for open-source prices
        alpha_vantage_api_key = getattr(self, "alpha_vantage_api_key", None)
        av_result = self.get_alpha_vantage_quote("NSEI", api_key=alpha_vantage_api_key)
        if av_result and av_result.get("last_price", 0) > 0:
            return av_result

        return {"symbol": symbol, "last_price": 0, "error": f"Quote not found for symbol: {symbol}. TrueData and Alpha Vantage failed. Please provide your Alpha Vantage API key."}

    async def get_historical_data(
        self, symbol: str, from_date: str, to_date: str
    ) -> list[dict]:
        """Get historical data from NSE (not implemented, see nsepython docs for options)."""
        # You can use nsepython's nsefetch or nse_historical to implement this if needed.
        return []
