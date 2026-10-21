from fugle_marketdata import RestClient
client = RestClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
stock = client.stock

# Check TAIEX
idx = stock.intraday.quote(symbol='0000')
print(f"TAIEX: changePercent={idx.get('changePercent')}%, openPrice={idx.get('openPrice')}, prevClose={idx.get('previousClose')}")

# Check a few stocks for their gaps
test_stocks = ['2330', '2454', '2317', '6505', '2324']
for sym in test_stocks:
    try:
        q = stock.intraday.quote(symbol=sym)
        op = q.get('openPrice') or 0
        pc = q.get('previousClose') or 0
        gap = (op - pc) / pc * 100 if pc > 0 else 0
        print(f"  {sym}: open={op}, prev={pc}, gap={gap:+.1f}%")
    except Exception as e:
        print(f"  {sym}: error {e}")

# Find top gainers
print("\nScanning for top gaps...")
tickers = stock.intraday.tickers(type='EQUITY', exchange='TWSE', isNormal=True)
symbols = [t['symbol'] for t in tickers.get('data', [])]

# Check first 100 for gaps
gaps = []
for sym in symbols[:200]:
    try:
        q = stock.intraday.quote(symbol=sym)
        op = q.get('openPrice') or 0
        pc = q.get('previousClose') or 0
        if pc >= 30 and pc <= 225 and op > 0:
            gap = (op - pc) / pc
            if gap > 0.03:
                gaps.append((sym, q.get('name',''), gap))
    except:
        pass

gaps.sort(key=lambda x: -x[2])
print(f"Found {len(gaps)} stocks with gap > 3% (first 200 checked)")
for g in gaps[:5]:
    print(f"  {g[0]} {g[1]}: {g[2]*100:.1f}%")
