"""
Rolling scan: subscribe 140 stocks, scan, cancel, next 140, scan...
All within 5 minutes of market open. Opening prices are static so late scans still work.
"""
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

BATCH = 100
total_gaps = []
total_valid = 0
t_start = time.time()

for batch_idx in range(0, len(all_stocks), BATCH):
    batch = all_stocks[batch_idx:batch_idx+BATCH]
    
    # Cancel previous batch (free up slots)
    if batch_idx > 0:
        prev_batch = all_stocks[batch_idx-BATCH:batch_idx]
        SK.SKQuoteLib_CancelRequestStocks(",".join(prev_batch))
    
    # Subscribe current batch
    stock_str = ",".join(batch)
    nc = SK.SKQuoteLib_RequestStocks(stock_str)
    if nc != 0:
        # Try individually
        valid_batch = []
        for code in batch:
            nc2 = SK.SKQuoteLib_RequestStocks(code)
            if nc2 == 0:
                valid_batch.append(code)
        batch = valid_batch
        if not batch:
            continue
    
    # Wait for data
    time.sleep(2)
    
    # Scan
    gaps_in_batch = 0
    valid_in_batch = 0
    for code in batch:
        for mk in [0, 1]:
            r = SK.SKQuoteLib_GetStockByStockNo(mk, code)
            if r.nCode != 0:
                continue
            dec = r.nDecimal if r.nDecimal > 0 else 2
            div = 10 ** dec
            op = r.nOpen / div
            pc = r.nRef / div
            if op > 0 and pc > 0:
                valid_in_batch += 1
                gap = (op - pc) / pc
                if abs(gap) >= 0.05:
                    total_gaps.append({
                        "code": code, "market": mk,
                        "open": op, "prev_close": pc,
                        "gap_pct": round(gap * 100, 2),
                        "close": r.nClose / div,
                        "volume": r.nTQty
                    })
                    gaps_in_batch += 1
                break
    
    total_valid += valid_in_batch
    elapsed = time.time() - t_start
    print(f"  Batch {batch_idx//BATCH+1}: {valid_in_batch} valid, {gaps_in_batch} gaps | elapsed: {elapsed:.1f}s")

total_time = time.time() - t_start
print(f"\n[DONE] Scanned {total_valid} stocks in {total_time:.1f}s")
print(f"  |gap|>=5%: {len(total_gaps)}")

if total_gaps:
    total_gaps.sort(key=lambda x: abs(x["gap_pct"]), reverse=True)
    print(f"\n  {'Code':<6} {'Gap%':>7} {'Open':>8} {'Prev':>8} {'Close':>8}")
    for g in total_gaps[:20]:
        print(f"  {g['code']:<6} {g['gap_pct']:>+6.1f}% {g['open']:>8.2f} {g['prev_close']:>8.2f} {g['close']:>8.2f}")

SK.Logout()
