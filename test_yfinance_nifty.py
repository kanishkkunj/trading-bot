import yfinance as yf

t = yf.Ticker('^NSEI')
print('fast_info:', t.fast_info)
print('last_price:', t.fast_info.get('last_price'))
