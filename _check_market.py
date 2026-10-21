from fugle_marketdata import RestClient
client = RestClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
stock = client.stock

# Calculate market gap from basket (same as the script does)
basket = ['2330', '2317', '2454', '2303', '6505', '3711', '2412']
gaps = []
for sym in basket:
    try:
        q = stock.intraday.quote(symbol=sym)
        op = q.get('openPrice') or 0
        pc = q.get('previousClose') or 0
        if pc > 0 and op > 0:
            g = (op - pc) / pc
            gaps.append(g)
            print(f"  {sym}: gap = {g*100:+.2f}%")
    except Exception as e:
        print(f"  {sym}: error")

market_gap = sum(gaps) / len(gaps) if gaps else 0
print(f"\nEstimated market gap: {market_gap*100:+.2f}%")

# Now check 2344 adjusted
q = stock.intraday.quote(symbol='2344')
op = q.get('openPrice', 0)
pc = q.get('previousClose', 0)
raw_gap = (op - pc) / pc
adj_gap = raw_gap - market_gap
print(f"\n2344:")
print(f"  Raw gap: {raw_gap*100:+.2f}%")
print(f"  Market gap: {market_gap*100:+.2f}%")
print(f"  Adjusted gap: {adj_gap*100:+.2f}%")
print(f"  Threshold: -5.00%")
print(f"  Signal: {'YES - LONG' if adj_gap < -0.05 else 'NO - filtered by market adjustment'}")
