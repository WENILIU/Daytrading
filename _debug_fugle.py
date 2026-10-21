from fugle_marketdata import RestClient
client = RestClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
stock = client.stock

# Check TAIEX
try:
    idx = stock.intraday.current(symbol='0000')
    print("TAIEX:", idx)
except Exception as e:
    print(f"TAIEX error: {e}")

# Check tickers
try:
    tickers = stock.intraday.tickers(type='EQUITY', exchange='TWSE', isNormal=True)
    data = tickers.get('data', [])
    print(f"Tickers count: {len(data)}")
    if data:
        t = data[0]
        keys = ['symbol','name','open','previousClose','changePercent']
        print("Sample:", {k: t.get(k) for k in keys})
        # Check for gap stocks
        gaps = []
        for t in data:
            pc = t.get('previousClose', 0)
            op = t.get('open', 0)
            if pc > 0 and op > 0:
                gap = (op - pc) / pc
                if gap > 0.05:
                    gaps.append((t['symbol'], t['name'], gap))
        print(f"Stocks with gap > 5%: {len(gaps)}")
        for g in sorted(gaps, key=lambda x: -x[2])[:5]:
            print(f"  {g[0]} {g[1]}: {g[2]*100:.1f}%")
except Exception as e:
    print(f"Tickers error: {e}")
