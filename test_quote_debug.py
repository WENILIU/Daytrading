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

price_received = [0]

class QEvent:
    def OnNotifyStockList(self, *a):
        print("    >> OnNotifyStockList fired!")
        return -1
    def OnNotifyPriceLONG(self, *a):
        price_received[0] += 1
        if price_received[0] <= 3:
            print(f"    >> OnNotifyPriceLONG #{price_received[0]}: market={a[0]}, idx={a[1]}")
        return -1
    def OnNotifyTicksLONG(self, *a): return -1
    def OnNotifyBest5LONG(self, *a): return -1

print("Creating objects...")
skC = cc.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
skQ = cc.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)
skR = cc.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)

print("Registering events...")
re_h = cc.GetEvents(skR, type('RE', (), {'OnReplyMessage': lambda s,a,b: -1})())
qe_h = cc.GetEvents(skQ, QEvent())

print("Login...")
skC.SKCenterLib_SetLogPath(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\CapitalLog")
nCode = skC.SKCenterLib_Login(CUST_ID, PASSWORD)
print(f"  Login: {nCode}")

print("EnterMonitor...")
nCode = skQ.SKQuoteLib_EnterMonitorLONG()
print(f"  EnterMonitor: {nCode}")

print("\nPumping messages for 10s...")
for i in range(100):
    pump()
    time.sleep(0.1)
print(f"  Price callbacks received: {price_received[0]}")

# Check quote status
print("\nGetQuoteStatus...")
try:
    status = skQ.SKQuoteLib_GetQuoteStatus()
    print(f"  Status: {status}")
except Exception as e:
    print(f"  Error: {e}")

# Try RequestStocks for 2330
print("\nRequestStocks('2330')...")
try:
    pn = sk.QUOTEQUERYFLAG()
    nCode = skQ.SKQuoteLib_RequestStocks(pn, "2330")
    print(f"  RequestStocks: code={nCode}")
except Exception as e:
    print(f"  Error: {e}")

print("Pumping 5s after request...")
for i in range(50):
    pump()
    time.sleep(0.1)
print(f"  Price callbacks total: {price_received[0]}")

# Try GetStockByNo
print("\nGetStockByNo('2330')...")
try:
    pStock = sk.SKSTOCKLONG()
    nCode, pStock = skQ.SKQuoteLib_GetStockByNoLONG("2330", pStock)
    print(f"  code={nCode}, open={pStock.nOpen}, ref={pStock.nRef}, name={pStock.bstrStockNo}")
except Exception as e:
    print(f"  Error: {e}")

# Try GetStockByMarketAndNo
print("\nGetStockByMarketAndNo(0, '2330')...")
try:
    pStock = sk.SKSTOCKLONG()
    nCode, pStock = skQ.SKQuoteLib_GetStockByMarketAndNo(0, "2330", pStock)
    print(f"  code={nCode}, open={pStock.nOpen}, ref={pStock.nRef}")
except Exception as e:
    print(f"  Error: {e}")
