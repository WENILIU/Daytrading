import sys, os, time, ctypes
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
os.add_dll_directory(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")

import comtypes.client
comtypes.client.GetModule(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll")
import comtypes.gen.SKCOMLib as sk

print("=" * 60)
print("SKCOM Quote Speed Test")
print("=" * 60)

m_pSKCenter = comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
m_pSKQuote = comtypes.client.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)
m_pSKReply = comtypes.client.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)

# Register ReplyLib FIRST (required before login)
class SKReplyEvent:
    def OnReplyMessage(self, bstrUserID, bstrMessages):
        return -1

reply_event = SKReplyEvent()
reply_handler = comtypes.client.GetEvents(m_pSKReply, reply_event)

# Login
print("\n[1] Login...")
nCode = m_pSKCenter.SKCenterLib_Login("D121280815", "Zaq582811@")
if nCode != 0:
    msg = m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
    print(f"  Login failed: {msg}")
    sys.exit(1)
print("  Login OK")

# Enter quote monitor
print("\n[2] EnterMonitor...")
t0 = time.time()
nCode = m_pSKQuote.SKQuoteLib_EnterMonitorLONG()
elapsed = time.time() - t0
if nCode != 0:
    msg = m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
    print(f"  Failed: {msg}")
    sys.exit(1)
print(f"  Connected in {elapsed:.2f}s")

# Wait for data
print("\n[3] Waiting 5s for quote data...")
time.sleep(5)

# Scan
print("\n[4] Scanning via GetStockByIndex...")
t0 = time.time()

total_stocks = 0
valid_stocks = 0
gap_candidates = []

for market_no in [0, 1]:
    idx = 0
    market_count = 0
    while idx < 5000:
        pSKStock = sk.SKSTOCKLONG()
        try:
            pSKStock, nCode = m_pSKQuote.SKQuoteLib_GetStockByIndexLONG(market_no, idx, pSKStock)
            if nCode != 0:
                break
        except:
            break

        stock_no = str(pSKStock.bstrStockNo)
        stock_name = str(pSKStock.bstrStockName)
        open_price = pSKStock.nOpen / 100.0
        prev_close = pSKStock.nRef / 100.0
        y_volume = pSKStock.nYQty

        idx += 1
        total_stocks += 1
        market_count += 1

        if open_price <= 0 or prev_close <= 0:
            continue
        valid_stocks += 1

        if prev_close > 0:
            gap = (open_price - prev_close) / prev_close
            if abs(gap) > 0.03:
                gap_candidates.append((stock_no, stock_name, open_price, prev_close, gap, y_volume))

    print(f"  Market {market_no}: {market_count} stocks")

scan_time = time.time() - t0

print(f"\n{'=' * 60}")
print(f"RESULTS")
print(f"{'=' * 60}")
print(f"  Total stocks: {total_stocks}")
print(f"  Valid (has price): {valid_stocks}")
print(f"  Scan time: {scan_time:.3f}s")
print(f"  Speed: {total_stocks/max(scan_time,0.001):.0f} stocks/sec")
print(f"\n  |gap| > 3%: {len(gap_candidates)} stocks")
if gap_candidates:
    gap_candidates.sort(key=lambda x: abs(x[4]), reverse=True)
    print(f"  Top 10:")
    for s, n, op, pc, g, v in gap_candidates[:10]:
        print(f"    {s} {n:<8} open={op:.1f} prev={pc:.1f} gap={g*100:+.1f}% vol={v:,}")

pass  # No logout method in SKCOM
print("\nDone.")
