import sys, os, time, ctypes
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\SKDLLPythonTester")
os.add_dll_directory(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
from SKDLLPython import SK

SK.OnReplyMessage(lambda a, b: None)
SK.OnNotifyQuoteLONG(lambda m, s: None)
SK.Login("D121280815", "Zaq582811@")
for t in [0, 1]:
    SK.ManageServerConnection("D121280815", 0, t)
time.sleep(3)

# Try calling LoadTWCommodity directly via DLL
dll = SK._dll
print("Trying SKQuoteLib_LoadTWCommodity...")
try:
    dll.SKQuoteLib_LoadTWCommodity.argtypes = [ctypes.c_int]
    dll.SKQuoteLib_LoadTWCommodity.restype = ctypes.c_int
    for mn in [0, 1]:
        r = dll.SKQuoteLib_LoadTWCommodity(mn)
        print(f"  Market {mn}: {r}")
except Exception as e:
    print(f"  Error: {e}")

time.sleep(3)

# Now try RequestStockList
for mn in [0, 1]:
    sl = SK.RequestStockList(mn)
    raw = sl.raw_data
    print(f"\nMarket {mn}: raw length={len(raw)}")
    if len(raw) > 100:
        codes = []
        for line in raw.replace('%', '\n').split('\n'):
            parts = line.strip().split(',')
            if parts and parts[0].strip().isdigit() and len(parts[0].strip()) == 4:
                codes.append(parts[0].strip())
        print(f"  Stocks: {len(codes)}")
        if codes:
            print(f"  Sample: {codes[:10]}")
            # Save to file
            with open("all_stocks.txt", "w") as f:
                f.write('\n'.join(codes))
            print(f"  Saved to all_stocks.txt")
    else:
        print(f"  Raw: {raw[:200]}")
