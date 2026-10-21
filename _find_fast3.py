import urllib.request
import ssl
import json
import time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch(url, timeout=10):
    req = urllib.request.urlopen(url, timeout=timeout, context=ctx)
    return req.read().decode('utf-8')

# Option 1: Fugle WebSocket
print("=== Fugle WebSocket ===")
try:
    import fugle_marketdata
    print(f"  fugle version: {fugle_marketdata.__version__}")
    # Check for websocket
    from fugle_marketdata import WebSocketClient
    print("  WebSocketClient available!")
except ImportError:
    print("  No WebSocketClient")
except Exception as e:
    print(f"  Error: {e}")

# Option 2: Check fugle for realtime/quote endpoints
print("\n=== Fugle endpoints ===")
try:
    from fugle_marketdata import RestClient
    client = RestClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
    # Check what's available
    stock = client.stock
    intraday = stock.intraday
    print(f"  intraday: {[x for x in dir(intraday) if not x.startswith('_')]}")
    snapshot = stock.snapshot
    print(f"  snapshot: {[x for x in dir(snapshot) if not x.startswith('_')]}")
except Exception as e:
    print(f"  Error: {e}")

# Option 3: Try TWSE with different IP/port
print("\n=== TWSE alternatives ===")
urls = [
    "https://twse-webquery.twse.com.tw/common/stock/",
    "http://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=20261019",
    "https://opendata.twse.com.tw/v2/opendata/codeserver/queryData.ashx?type=STK&code=2330",
]
for url in urls:
    try:
        start = time.time()
        data = fetch(url, timeout=8)
        elapsed = time.time() - start
        print(f"  OK ({elapsed:.1f}s): {url[:60]}...")
        print(f"    {data[:150]}")
    except Exception as e:
        print(f"  FAIL: {url[:60]}... - {str(e)[:50]}")

# Option 4: 群益网上發 actual API (from browser network tab)
print("\n=== Capital internal API ===")
urls = [
    "https://tradeweb.capital.com.tw/StockAPI/GetStockList",
    "https://tradeweb.capital.com.tw/api/stock/list",
]
for url in urls:
    try:
        data = fetch(url, timeout=5)
        print(f"  OK: {data[:100]}")
    except Exception as e:
        print(f"  {str(e)[:60]}")
