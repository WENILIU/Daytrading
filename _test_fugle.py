import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from fugle_marketdata import RestClient

client = RestClient(api_key="MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==")
stock = client.stock

# Try to get today's 1-min candles for 6756 (one of today's signals)
try:
    data = stock.intraday.candles(symbol="6756", type="TICK", interval="MIN1")
    print(f"Type: {type(data)}")
    if isinstance(data, dict):
        print(f"Keys: {list(data.keys())}")
        items = data.get("data", [])
        print(f"Records: {len(items)}")
        if items:
            print(f"First: {items[0]}")
            print(f"Last: {items[-1]}")
    elif isinstance(data, list):
        print(f"Records: {len(data)}")
        if data:
            print(f"First: {data[0]}")
except Exception as e:
    print(f"Error: {e}")

# Also try the realtime quote to see what data is available
try:
    q = stock.intraday.quote(symbol="6756")
    print(f"\nQuote keys: {list(q.keys())}")
    print(f"openPrice: {q.get('openPrice')}")
    print(f"previousClose: {q.get('previousClose')}")
    print(f"close: {q.get('close')}")
except Exception as e:
    print(f"Quote error: {e}")
