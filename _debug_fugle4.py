from fugle_marketdata import RestClient
client = RestClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
stock = client.stock

# Try snapshot.movers (likely gives top gainers/losers)
try:
    r = stock.snapshot.movers(type='EQUITY', exchange='TWSE')
    print("movers:", type(r))
    if isinstance(r, dict):
        print("Keys:", list(r.keys()))
        for k, v in r.items():
            if isinstance(v, list) and v:
                print(f"  {k}: {len(v)} items")
                print(f"    First: {v[0]}")
                break
except Exception as e:
    print(f"movers error: {e}")

# Try snapshot.quotes
try:
    r = stock.snapshot.quotes(symbols='2330,2454,2317')
    print("\nquotes batch:", type(r))
    if isinstance(r, list):
        print(f"  {len(r)} items")
        if r:
            print("  First:", {k: r[0].get(k) for k in ['symbol','openPrice','previousClose','changePercent']})
    elif isinstance(r, dict):
        print("  Keys:", list(r.keys()))
except Exception as e:
    print(f"quotes error: {e}")

# Try ticker for full data
try:
    r = stock.intraday.ticker(symbol='2330')
    print("\nticker 2330 full:")
    print("  openPrice:", r.get('openPrice'))
    print("  previousClose:", r.get('previousClose'))
    print("  changePercent:", r.get('changePercent'))
except Exception as e:
    print(f"ticker error: {e}")
