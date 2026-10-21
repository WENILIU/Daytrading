from fugle_marketdata import RestClient
import time

client = RestClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
stock = client.stock

# Try snapshot endpoints with correct params
print("=== snapshot.actives ===")
try:
    r = stock.snapshot.actives(market='TSE', type='EQUITY')
    print(f"  Type: {type(r)}, keys: {list(r.keys()) if isinstance(r, dict) else 'list'}")
    if isinstance(r, dict):
        for k, v in r.items():
            if isinstance(v, list) and v:
                print(f"  {k}: {len(v)} items, first: {v[0]}")
                break
except Exception as e:
    print(f"  Error: {e}")

print("\n=== snapshot.movers ===")
try:
    r = stock.snapshot.movers(market='TSE', type='EQUITY')
    print(f"  Type: {type(r)}")
    if isinstance(r, dict):
        for k, v in r.items():
            if isinstance(v, list) and v:
                print(f"  {k}: {len(v)} items")
                print(f"    First: {v[0]}")
                break
except Exception as e:
    print(f"  Error: {e}")

print("\n=== snapshot.quotes (all) ===")
try:
    r = stock.snapshot.quotes(market='TSE')
    print(f"  Type: {type(r)}, len: {len(r) if isinstance(r, list) else 'dict'}")
    if isinstance(r, list) and r:
        print(f"  First: {r[0]}")
except Exception as e:
    print(f"  Error: {e}")

print("\n=== intraday.tickers with sort ===")
start = time.time()
try:
    r = stock.intraday.tickers(type='EQUITY', exchange='TWSE', sort='changePercent', order='desc')
    data = r.get('data', [])
    elapsed = time.time() - start
    print(f"  {len(data)} items in {elapsed:.2f}s")
    if data:
        print(f"  Keys: {list(data[0].keys())}")
        print(f"  First: {data[0]}")
except Exception as e:
    print(f"  Error: {e}")
