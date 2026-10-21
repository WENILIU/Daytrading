"""
SKCOM Scan Speed Test v6 - minimal flow
"""
import sys, os, time
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\SKDLLPythonTester")
os.add_dll_directory(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
from SKDLLPython import SK

CUST_ID = "D121280815"
PASSWORD = "Zaq582811@"

print("=" * 60)
print("SKCOM SCAN TEST v6")
print("=" * 60)

# Setup
SK.OnReplyMessage(lambda a, b: None)
SK.OnNotifyQuoteLONG(lambda m, s: None)

# Login
r = SK.Login(CUST_ID, PASSWORD)
print(f"\nLogin: {SK.GetMessage(r.Code)}")
if r.Code != 0: sys.exit(1)

# Connect quote
print("ManageServerConnection...")
for t in range(5):
    r = SK.ManageServerConnection(CUST_ID, 0, t)
    if r == 0:
        print(f"  target {t}: OK")

# Wait for connection to establish
print("Waiting 5s for quote connection...")
time.sleep(5)

# Subscribe to test stocks
test_codes = "2330,2454,2317,2303,6505,2324,2383,3711,2412,2357,2881,2882,2883,2884,2885"
print(f"\nRequestStocks ({len(test_codes.split(','))} stocks)...")
r = SK.SKQuoteLib_RequestStocks(test_codes)
print(f"  Result: {SK.GetMessage(r)}")

# Wait for data
print("Waiting 3s for data...")
time.sleep(3)

# Read
print("\nReading prices:")
for code in test_codes.split(','):
    data = SK.SKQuoteLib_GetStockByStockNo(0, code)
    if data.nCode == 0 and data.nOpen > 0:
        dec = data.nDecimal if data.nDecimal > 0 else 2
        div = 10 ** dec
        print(f"  {code}: open={data.nOpen/div:.2f} ref={data.nRef/div:.2f} close={data.nClose/div:.2f}")
    else:
        print(f"  {code}: no data (code={data.nCode})")

# Now try ALL stocks via GetStockByStockNo with a bigger list
print("\n--- Testing larger batch ---")
# Get stock list from COM version (which worked before - 10000 entries)
import comtypes.client as cc
cc.GetModule(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll")
import comtypes.gen.SKCOMLib as sk_com

skQ = cc.CreateObject(sk_com.SKQuoteLib, interface=sk_com.ISKQuoteLib)
# Register events
skR = cc.CreateObject(sk_com.SKReplyLib, interface=sk_com.ISKReplyLib)
cc.GetEvents(skR, type('RE', (), {'OnReplyMessage': lambda s,a,b: -1})())
cc.GetEvents(skQ, type('QE', (), {'OnNotifyStockList': lambda s,*a: -1, 'OnNotifyPriceLONG': lambda s,*a: -1, 'OnNotifyTicksLONG': lambda s,*a: -1, 'OnNotifyBest5LONG': lambda s,*a: -1})())

# EnterMonitor on COM side too
nCode = skQ.SKQuoteLib_EnterMonitorLONG()
print(f"COM EnterMonitor: {nCode}")

# Try GetStockByIndex via COM
print("\nCOM GetStockByIndex test:")
total = 0
valid = 0
for market_no in [0, 1]:
    idx = 0
    while idx < 5000:
        pStock = sk_com.SKSTOCKLONG()
        try:
            pStock, nCode = skQ.SKQuoteLib_GetStockByIndexLONG(market_no, idx, pStock)
            if nCode != 0: break
        except: break
        total += 1
        if pStock.nOpen > 0 and pStock.nRef > 0:
            valid += 1
        idx += 1

print(f"  COM: total={total}, valid={valid}")

# If COM has data, use it!
if valid > 0:
    print("\n  => COM version works after ManageServerConnection!")
    # Scan for gaps
    gaps = []
    for market_no in [0, 1]:
        idx = 0
        while idx < 5000:
            pStock = sk_com.SKSTOCKLONG()
            try:
                pStock, nCode = skQ.SKQuoteLib_GetStockByIndexLONG(market_no, idx, pStock)
                if nCode != 0: break
            except: break
            op = pStock.nOpen / 100.0
            pc = pStock.nRef / 100.0
            if op > 0 and pc > 0:
                gap = (op - pc) / pc
                if abs(gap) >= 0.03:
                    gaps.append((str(pStock.bstrStockNo), op, pc, gap))
            idx += 1
    
    gaps.sort(key=lambda x: abs(x[3]), reverse=True)
    print(f"  |gap|>=3%: {len(gaps)}")
    for g in gaps[:15]:
        print(f"    {g[0]:<8} open={g[1]:>8.2f} prev={g[2]:>8.2f} gap={g[3]*100:>+6.1f}%")
