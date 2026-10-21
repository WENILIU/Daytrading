import sys, time
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\SKDLLPythonTester")
from SKDLLPython import SK

CUST_ID = "D121280815"
PASSWORD = "Zaq582811@"

# MUST register before login!
def on_reply(login_id, msg):
    pass
SK.OnReplyMessage(on_reply)

def on_conn(login_id, code):
    pass
SK.OnConnection(on_conn)

result = SK.Login(CUST_ID, PASSWORD)
print(f"[1] Login: {result.Code}")
if result.Code != 0:
    print(f"  {SK.GetMessage(result.Code)}")
    sys.exit(1)
print("  SUCCESS")

# Connect quote servers
for t in range(5):
    nc = SK.ManageServerConnection(CUST_ID, 0, t)
    print(f"[2] Target {t}: {nc} ({SK.GetMessage(nc)})")

time.sleep(2)

# Load commodity + RequestStockList
print("[3] LoadCommodity + RequestStockList...")
for mk in [0, 1]:
    nc = SK.LoadCommodity(mk)
    print(f"  LoadCommodity({mk}): {nc} ({SK.GetMessage(nc)})")

for mk in [0, 1]:
    try:
        r = SK.RequestStockList(mk)
        cnt = len(r.codes) if hasattr(r, "codes") else "unknown"
        print(f"  RequestStockList({mk}): {cnt} codes")
    except Exception as e:
        print(f"  RequestStockList({mk}): ERROR {e}")

# Subscribe stocks in batches
with open(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\all_stocks.txt") as f:
    all_stocks = [s.strip() for s in f if s.strip()]

batch_size = 200
total_ok = 0
for i in range(0, len(all_stocks), batch_size):
    batch = all_stocks[i:i+batch_size]
    stock_str = ",".join(batch)
    nc = SK.SKQuoteLib_RequestStocks(stock_str)
    if nc == 0:
        total_ok += len(batch)
        print(f"  Batch {i//batch_size+1}: {len(batch)} OK (total: {total_ok})")
    else:
        print(f"  Batch {i//batch_size+1}: FAILED {nc} ({SK.GetMessage(nc)})")
        break

print(f"[4] Subscribed: {total_ok}")
print("[5] Waiting 5s...")
time.sleep(5)

# Scan
print("[6] SCANNING...")
t0 = time.time()
total = 0; valid = 0; gaps = []
for code in all_stocks[:total_ok]:
    for mk in [0, 1]:
        r = SK.SKQuoteLib_GetStockByStockNo(mk, code)
        if r.code != 0:
            continue
        dec = r.sDecimal if r.sDecimal > 0 else 2
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
