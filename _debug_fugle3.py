from fugle_marketdata import RestClient
client = RestClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
stock = client.stock

# Check snapshot
try:
    snap = stock.snapshot
    print("snapshot methods:", [x for x in dir(snap) if not x.startswith('_')])
except Exception as e:
    print(f"snapshot error: {e}")

# Try ticker (singular)
try:
    r = stock.intraday.ticker(symbol='2330')
    print("\nticker 2330:", type(r))
    if isinstance(r, dict):
        print("Keys:", list(r.keys())[:10])
except Exception as e:
    print(f"ticker error: {e}")

# Try tickers with sort/limit to see if data comes
try:
    r = stock.intraday.tickers(type='EQUITY', exchange='TWSE', sort='changePercent', order='desc', limit=10)
    data = r.get('data', [])
    print(f"\ntickers sorted: {len(data)} items")
    if data:
        print("First item keys:", list(data[0].keys()))
        print("First:", data[0])
except Exception as e:
    print(f"tickers sorted error: {e}")
