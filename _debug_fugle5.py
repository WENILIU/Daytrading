from fugle_marketdata import RestClient
import time
client = RestClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
stock = client.stock

# Try snapshot.quotes with market param
try:
    r = stock.snapshot.quotes(symbols='2330,2454', market='TSE')
    print("snapshot.quotes:", type(r))
    if isinstance(r, list):
        print(f"  {len(r)} items")
        for item in r[:2]:
            print(f"  {item.get('symbol')}: open={item.get('openPrice')}, prev={item.get('previousClose')}")
except Exception as e:
    print(f"snapshot.quotes error: {e}")

# Try with different params
try:
    r = stock.snapshot.quotes(symbols='2330,2454', exchange='TWSE')
    print("\nsnapshot.quotes exchange:", type(r))
    if isinstance(r, list):
        print(f"  {len(r)} items")
        for item in r[:2]:
            print(f"  {item.get('symbol')}: open={item.get('openPrice')}, prev={item.get('previousClose')}")
except Exception as e:
    print(f"snapshot.quotes exchange error: {e}")

# Time how long quote() takes for one stock
start = time.time()
r = stock.intraday.quote(symbol='2330')
elapsed = time.time() - start
print(f"\nSingle quote time: {elapsed:.3f}s")
print(f"  openPrice: {r.get('openPrice')}, prevClose: {r.get('previousClose')}")

# Estimate: 1500 stocks at this rate
print(f"  Estimated for 1500 stocks: {elapsed * 1500:.0f}s")
