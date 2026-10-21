import comtypes.client
import ctypes
import ctypes.wintypes
import time

comtypes.client.GetModule(r'D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll')
import comtypes.gen.SKCOMLib as sk

user32 = ctypes.windll.user32

class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("message", ctypes.wintypes.UINT),
        ("wParam", ctypes.wintypes.WPARAM),
        ("lParam", ctypes.wintypes.LPARAM),
        ("time", ctypes.wintypes.DWORD),
        ("pt", ctypes.wintypes.POINT),
    ]

def pump_messages():
    """Pump Windows messages to allow COM callbacks"""
    msg = MSG()
    while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):  # PM_REMOVE=1
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

m_pSKCenter = comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
m_pSKReply = comtypes.client.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)
m_pSKQuote = comtypes.client.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)

class RE:
    def OnReplyMessage(self, a, b): return -1
h = comtypes.client.GetEvents(m_pSKReply, RE())

m_pSKCenter.SKCenterLib_SetAuthority(0)
m_pSKCenter.SKCenterLib_Login('D121280815', 'Zaq582811@')

# Enter monitor
m_pSKQuote.SKQuoteLib_EnterMonitorLONG()

# Pump messages while waiting for connection
print("Pumping messages, waiting for quote connection...")
connected = False
for i in range(60):
    pump_messages()
    time.sleep(0.5)
    try:
        nCode = m_pSKQuote.SKQuoteLib_IsConnected()
        if nCode == 0:
            print(f"  CONNECTED at {i*0.5:.1f}s!")
            connected = True
            break
    except:
        pass
    if i % 10 == 0:
        print(f"  [{i*0.5:.1f}s] still waiting...")

if not connected:
    print("  Not connected after 30s. Trying anyway...")

# Try getting data
print("\nGetStockByNoLONG('2344'):")
p = sk.SKSTOCKLONG()
r = m_pSKQuote.SKQuoteLib_GetStockByNoLONG("2344", p)
if isinstance(r, list):
    sd, nc = r[0], r[1]
    print(f"  nCode: {nc}")
    if nc == 0:
        print(f"  2344: open={sd.nOpen}, ref={sd.nRef}")
        print(f"  Actual: open={sd.nOpen/10:.1f}, ref={sd.nRef/10:.1f}")
    else:
        print(f"  {m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nc)}")
