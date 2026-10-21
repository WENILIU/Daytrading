from fugle_marketdata import RestClient
client = RestClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
stock = client.stock

# Check individual stocks
test_stocks = ['2330', '2454', '2317', '6505', '2324', '3711', '2412']
for sym in test_stocks:
    try:
        q = stock.intraday.quote(symbol=sym)
        op = q.get('openPrice') or 0
        pc = q.get('previousClose') or 0
        gap = (op - pc) / pc * 100 if pc > 0 else 0
        print(f"  {sym}: open={op}, prev={pc}, gap={gap:+.2f}%")
    except Exception as e:
        print(f"  {sym}: ERROR - {e}")

# Try to get TAIEX via different method
print("\nTAIEX attempts:")
try:
    r = stock.intraday.quote(symbol='0000', market='TSE')
    print(f"  quote 0000 market=TSE: {r.get('changePercent')}")
except Exception as e:
    print(f"  quote 0000: {e}")

# Try index endpoint
try:
    r = client.index.intraday.quote(symbol='0000')
    print(f"  index.quote: {r}")
except Exception as e:
    print(f"  index.quote: {e}")

# Check if there's an index client
print(f"\nclient attrs: {[x for x in dir(client) if not x.startswith('_')]}")
