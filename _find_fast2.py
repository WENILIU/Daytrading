import urllib.request
import ssl
import json
import time

# Disable SSL verification
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch(url, timeout=10):
    req = urllib.request.urlopen(url, timeout=timeout, context=ctx)
    return req.read().decode('utf-8')

# Option 1: TWSE tick data (all stocks)
print("=== TWSE tick (140.112.29.14) ===")
try:
    start = time.time()
    data = fetch("http://140.112.29.14:80/stock_json/", timeout=15)
    elapsed = time.time() - start
    parsed = json.loads(data)
    print(f"  Time: {elapsed:.2f}s, size: {len(data)} bytes")
    if isinstance(parsed, dict):
        keys = list(parsed.keys())
        print(f"  Stocks: {len(keys)}")
        # Show first stock data
        first_key = keys[0]
        print(f"  Sample [{first_key}]: {parsed[first_key]}")
except Exception as e:
    print(f"  Error: {e}")

# Option 2: TPEx with SSL bypass
print("\n=== TPEx ===")
try:
    start = time.time()
    data = fetch("https://www.tpex.org.tw/web/stock/aftertrading/stockinfo/bd.php?l=zh-tw&s=0,asc,0")
    elapsed = time.time() - start
    parsed = json.loads(data)
    print(f"  Time: {elapsed:.2f}s")
    if 'data' in parsed:
        print(f"  Items: {len(parsed['data'])}")
        if parsed['data']:
            print(f"  First: {parsed['data'][0]}")
except Exception as e:
    print(f"  Error: {e}")

# Option 3: 群益网上發 internal API (the web page must call something)
print("\n=== Capital web API ===")
try:
    # The web trading page likely uses an internal API
    url = "https://tradeweb.capital.com.tw/api/stock/realtime"
    data = fetch(url, timeout=5)
    print(f"  OK: {data[:200]}")
except Exception as e:
    print(f"  Error: {e}")

# Option 4: Yahoo Finance batch
print("\n=== Yahoo Finance ===")
try:
    symbols = "2330.TW,2454.TW,2317.TW"
    url = f"https://query1.finance.yahoo.com/v8/finance/quote?symbols={symbols}"
    data = fetch(url, timeout=10)
    parsed = json.loads(data)
    results = parsed.get('quoteResponse', {}).get('result', [])
    print(f"  Got {len(results)} quotes")
    if results:
        r = results[0]
        print(f"  {r.get('symbol')}: open={r.get('regularMarketOpen')}, prevClose={r.get('regularMarketPreviousClose')}")
except Exception as e:
    print(f"  Error: {e}")
