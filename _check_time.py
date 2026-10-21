import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from datetime import datetime
from fugle_marketdata import RestClient

print(f"Current time: {datetime.now()}")

# Fugle real-time check
client = RestClient(api_key="MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==")
q = client.stock.intraday.quote(symbol="2330")
print(f"\n=== Fugle ===")
print(f"lastPrice: {q.get('lastPrice')}")
print(f"lastTrade: {q.get('lastTrade')}")
print(f"openPrice: {q.get('openPrice')}")
print(f"previousClose: {q.get('previousClose')}")
print(f"lastUpdated: {q.get('lastUpdated')}")

# Yahoo comparison
import requests
session = requests.Session()
session.headers["User-Agent"] = "Mozilla/5.0"
session.get("https://fc.yahoo.com", timeout=5, allow_redirects=True)
r = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=5)
crumb = r.text.strip()
url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols=2330.TW&crumb={crumb}"
r = session.get(url, timeout=5)
yq = r.json()["quoteResponse"]["result"][0]
print(f"\n=== Yahoo ===")
print(f"regularMarketPrice: {yq.get('regularMarketPrice')}")
import datetime as dt
ts = yq.get("regularMarketTime", 0)
print(f"Last trade: {dt.datetime.fromtimestamp(ts)}")
print(f"prevClose: {yq.get('regularMarketPreviousClose')}")

print(f"\n=== Comparison ===")
print(f"Fugle price: {q.get('lastPrice')}")
print(f"Yahoo price: {yq.get('regularMarketPrice')}")
print(f"Match: {q.get('lastPrice') == yq.get('regularMarketPrice')}")
