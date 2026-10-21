from fugle_marketdata import RestClient
client = RestClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
stock = client.stock

# Check available methods
print("stock methods:", [x for x in dir(stock) if not x.startswith('_')])
print()

# Check intraday methods
intraday = stock.intraday
print("intraday methods:", [x for x in dir(intraday) if not x.startswith('_')])
print()

# Try different endpoints
# 1. realTimeQuote
try:
    r = stock.intraday.realTimeQuote(symbol='2330')
    print("realTimeQuote 2330:", r)
except Exception as e:
    print(f"realTimeQuote error: {e}")

# 2. Try tickers with different params
try:
    r = stock.intraday.tickers(type='EQUITY', exchange='TWSE', isRealtime=True)
    data = r.get('data', [])
    print(f"\ntickers isRealtime=True: {len(data)} items")
    if data:
        t = data[0]
        print("Fields:", list(t.keys())[:10])
        print("Sample:", {k: t.get(k) for k in ['symbol','open','close','previousClose']})
except Exception as e:
    print(f"tickers isRealtime error: {e}")

# 3. Try the quote endpoint
try:
    r = stock.intraday.quote(symbol='2330')
    print(f"\nquote 2330: {r}")
except Exception as e:
    print(f"quote error: {e}")
