import sys, time
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\SKDLLPythonTester")
from SKDLLPython import SK

CUST_ID = "D121280815"
PASSWORD = "Zaq582811@"

def on_reply(login_id, msg): pass
def on_conn(login_id, code): pass
SK.OnReplyMessage(on_reply)
SK.OnConnection(on_conn)

result = SK.Login(CUST_ID, PASSWORD)
if result.Code != 0:
    print(f"Login failed: {result.Code}"); sys.exit(1)
print("[1] Login OK")

for t in [0, 1, 4]:
    SK.ManageServerConnection(CUST_ID, 0, t)
print("[2] Connected")
time.sleep(2)

with open("all_stocks.txt") as f:
    all_stocks = [s.strip() for s in f if s.strip()]

# Subscribe with error recovery: batch of 100, split on failure
def subscribe_batch(stocks):
    """Try to subscribe a batch. On failure, split and retry."""
    if not stocks:
        return []
    stock_str = ",".join(stocks)
    nc = SK.SKQuoteLib_RequestStocks(stock_str)
    if nc == 0:
        return stocks
    # Split in half and retry
    if len(stocks) == 1:
        return []  # single stock failed, skip it
    mid = len(stocks) // 2
    left = subscribe_batch(stocks[:mid])
    right = subscribe_batch(stocks[mid:])
    return left + right

print(f"[3] Subscribing {len(all_stocks)} stocks (batch=100, auto-recover)...")
t0 = time.time()
valid_stocks = []
batch_size = 100
for i in range(0, len(all_stocks), batch_size):
    batch = all_stocks[i:i+batch_size]
    ok = subscribe_batch(batch)
    valid_stocks.extend(ok)
    if len(ok) < len(batch):
        print(f"  Batch {i//batch_size+1}: {len(ok)}/{len(batch)} valid")

sub_time = time.time() - t0
print(f"[4] Subscribed: {len(valid_stocks)}/{len(all_stocks)} in {sub_time:.1f}s")

# Save valid list
with open("valid_stocks.txt", "w") as f:
    f.write("\n".join(valid_stocks))

print("[5] Waiting 5s for data...")
time.sleep(5)

# Scan
print("[6] SCANNING...")
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
print(f"  |gap|>=3%:{len(gaps)} |gap|>=5%:{len([g for g in gaps if abs(g[4])>=5])}")
if gaps:
    gaps.sort(key=lambda x: abs(x[4]), reverse=True)
    for g in gaps[:20]:
        print(f"    {g[0]:<6} gap={g[4]:+.1f}% open={g[2]:.2f} prev={g[3]:.2f}")
