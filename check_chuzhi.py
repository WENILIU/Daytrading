import pickle, pandas as pd, numpy as np
from fugle_marketdata import RestClient
import warnings
warnings.filterwarnings('ignore')

# First, check if Fugle API has any 處置 indicator
client = RestClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')

# Check a stock quote for any trading restriction fields
q = client.stock.intraday.quote(symbol='2429')
print("=== Fugle quote fields ===")
for k, v in sorted(q.items()):
    if k not in ['bids', 'asks', 'total', 'lastTrade', 'lastTrial']:
        print(f"  {k}: {v}")

# Check if there's a "dealCode" or trading method field
print("\n\n=== Checking stock info for trading restrictions ===")
try:
    info = client.stock.basic.info(symbol='2429')
    print("Stock info fields:", list(info.keys()))
    for k, v in info.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"  Error: {e}")

# Try the tickers endpoint - might have dealCode
print("\n\n=== Checking tickers for dealCode ===")
try:
    tickers = client.stock.intraday.tickers(type="EQUITY", exchange="TWSE", isNormal=True)
    sample = tickers.get('data', [])[:3]
    for t in sample:
        print(f"  Fields: {list(t.keys())}")
        break
except Exception as e:
    print(f"  Error: {e}")
