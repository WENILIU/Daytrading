from fugle_marketdata import RestClient
client = RestClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
q = client.stock.intraday.quote(symbol='2344')
op = q.get('openPrice', 0)
pc = q.get('previousClose', 0)
cl = q.get('closePrice', 0) or q.get('lastPrice', 0)
low = q.get('lowPrice', 0)
gap = (op - pc) / pc * 100 if pc else 0
intraday = (cl - op) / op * 100 if op else 0

print("2344 仁寶:")
print(f"  前收: {pc}")
print(f"  開盤: {op} (gap = {gap:+.2f}%)")
print(f"  最低: {low}")
print(f"  現價: {cl}")
print(f"  盤中跌幅: {intraday:+.2f}%")
print()
print("策略條件: 開盤 gap 必須 < -5% 才觸發 LONG")
print(f"實際開盤 gap: {gap:+.2f}%")
if gap < -5:
    print("=> 符合條件，應該進場")
else:
    print("=> 不符合（開盤跌幅未達 -5%）")
    print()
    print("注意：策略看的是「開盤跳空幅度」，不是「盤中跌幅」")
    print("2344 可能是開盤只跌 2-3%，然後盤中繼續跌到 -6%")
    print("這種情況不會觸發信號，因為開盤時沒有跳空超過 5%")
