import sys, os, time, ctypes, ctypes.wintypes
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
os.add_dll_directory(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
import comtypes.client as cc
cc.GetModule(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll")
import comtypes.gen.SKCOMLib as sk

CUST_ID = "D121280815"
PASSWORD = "Zaq582811@"

user32 = ctypes.windll.user32
class MSG(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.wintypes.HWND), ("message", ctypes.wintypes.UINT),
                ("wParam", ctypes.wintypes.WPARAM), ("lParam", ctypes.wintypes.LPARAM),
                ("time", ctypes.wintypes.DWORD), ("pt", ctypes.wintypes.POINT)]
def pump():
    msg = MSG()
    while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

price_count = [0]
class QEvent:
    def OnNotifyStockList(self, *a):
        print("  >> StockList received!")
        return -1
    def OnNotifyPriceLONG(self, *a):
        price_count[0] += 1
        return -1
    def OnNotifyTicksLONG(self, *a): return -1
    def OnNotifyBest5LONG(self, *a): return -1

skC = cc.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
skQ = cc.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)
skR = cc.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)

re_h = cc.GetEvents(skR, type('RE', (), {'OnReplyMessage': lambda s,a,b: -1})())
qe_h = cc.GetEvents(skQ, QEvent())

skC.SKCenterLib_SetLogPath(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\CapitalLog")

# Method 1: Normal login + EnterMonitor
print("=== Method 1: Login + EnterMonitor ===")
nCode = skC.SKCenterLib_Login(CUST_ID, PASSWORD)
print(f"  Login: {nCode}")
nCode = skQ.SKQuoteLib_EnterMonitorLONG()
print(f"  EnterMonitor: {nCode}")
for i in range(50):
    pump()
    time.sleep(0.1)
print(f"  Prices: {price_count[0]}")
status = skQ.SKQuoteLib_GetQuoteStatus()
print(f"  Status: {status}")

# Method 2: Try LoginSetQuote
print("\n=== Method 2: LoginSetQuote ===")
try:
    nCode = skC.SKCenterLib_LoginSetQuote(CUST_ID, PASSWORD)
    print(f"  LoginSetQuote: {nCode}")
    if nCode == 0:
        nCode2 = skQ.SKQuoteLib_EnterMonitorLONG()
        print(f"  EnterMonitor: {nCode2}")
        for i in range(50):
            pump()
            time.sleep(0.1)
        print(f"  Prices: {price_count[0]}")
        status = skQ.SKQuoteLib_GetQuoteStatus()
        print(f"  Status: {status}")
except Exception as e:
    print(f"  Error: {e}")

# Method 3: Try EnterMonitorLONGByMarket
print("\n=== Method 3: EnterMonitorLONGByMarket ===")
try:
    nCode = skQ.SKQuoteLib_EnterMonitorLONGByMarket(0)
    print(f"  EnterMonitorByMarket(0): {nCode}")
    for i in range(30):
        pump()
        time.sleep(0.1)
    print(f"  Prices: {price_count[0]}")
except Exception as e:
    print(f"  Error: {e}")

# Method 4: Check if we need to use the non-LONG version
print("\n=== Method 4: EnterMonitor (non-LONG) ===")
try:
    nCode = skQ.SKQuoteLib_EnterMonitor()
    print(f"  EnterMonitor: {nCode}")
    for i in range(30):
        pump()
        time.sleep(0.1)
    print(f"  Prices: {price_count[0]}")
    # Try GetStockByIndex (non-LONG version might use different data)
    total = 0
    for market_no in [0, 1]:
        idx = 0
        while idx < 5000:
            pStock = sk.SKSTOCK()
            try:
                nCode = skQ.SKQuoteLib_GetStockByIndex(market_no, idx, pStock)
                if nCode != 0: break
                total += 1
                idx += 1
            except:
                break
    print(f"  Non-LONG stocks: {total}")
except Exception as e:
    print(f"  Error: {e}")

print(f"\nTotal price callbacks: {price_count[0]}")
