import sys, time
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\SKDLLPythonTester")
from SKDLLPython import SK

CUST_ID = "D121280815"
PASSWORD = "Zaq582811@"

def on_reply(login_id, msg): pass
def on_conn(login_id, code): pass
quote_count = [0]
def on_quote(market, stock_no):
    quote_count[0] += 1
SK.OnReplyMessage(on_reply)
SK.OnConnection(on_conn)
SK.OnNotifyQuoteLONG(on_quote)

result = SK.Login(CUST_ID, PASSWORD)
if result.Code != 0:
    print(f"Login failed: {result.Code}"); sys.exit(1)
print("[1] Login OK")

for t in [0, 1, 4]:
    SK.ManageServerConnection(CUST_ID, 0, t)
print("[2] Connected")
time.sleep(2)

# Subscribe first 200 only (within known limit)
with open("all_stocks.txt") as f:
    all_stocks = [s.strip() for s in f if s.strip()]

# Subscribe in batches of 100, max 200 total
batch_size = 100
valid_stocks = []
for i in range(0, min(200, len(all_stocks)), batch_size):
    batch = all_stocks[i:i+batch_size]
    stock_str = ",".join(batch)
    nc = SK.SKQuoteLib_RequestStocks(stock_str)
    if nc == 0:
        valid_stocks.extend(batch)
        print(f"  Batch {i//batch_size+1}: OK ({len(valid_stocks)} total)")
    else:
        print(f"  Batch {i//batch_size+1}: FAILED {nc}")

print(f"[3] Subscribed: {len(valid_stocks)}")
print(f"[4] Waiting 10s (tracking quote events)...")
for s in range(10):
    time.sleep(1)
    print(f"  t={s+1}s: {quote_count[0]} quote events")

# Scan
print("[5] SCANNING...")
t0 = time.time()
total = 0; valid = 0; gaps = []
for code in valid_stocks:
    for mk in [0, 1]:
        r = SK.SKQuoteLib_GetStockByStockNo(mk, code)
        if r.nCode != 0:
            continue
        dec = r.nDecimal if r.nDecimal > 0 else 2
        div = 10 ** dec
        op = r.nOpen / div
        pc = r.nRef / div
        if op > 0 and pc > 0:
            total += 1
            valid += 1
            gap = (op - pc) / pc
            if abs(gap) >= 0.03:
                gaps.append((code, mk, op, pc, round(gap * 100, 2)))
            break

scan_time = time.time() - t0
print(f"  Total:{total} Valid:{valid} Time:{scan_time:.3f}s")
print(f"  |gap|>=3%:{len(gaps)}")
if gaps:
    gaps.sort(key=lambda x: abs(x[4]), reverse=True)
    for g in gaps[:10]:
        print(f"    {g[0]:<6} gap={g[4]:+.1f}% open={g[2]:.2f} prev={g[3]:.2f}")
