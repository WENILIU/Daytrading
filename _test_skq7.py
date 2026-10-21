import comtypes.client
import ctypes
import time

comtypes.client.GetModule(r'D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll')
import comtypes.gen.SKCOMLib as sk

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

# Poll IsConnected
print("Polling IsConnected...")
for i in range(30):
    try:
        nCode = m_pSKQuote.SKQuoteLib_IsConnected()
        status = m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
        if i % 5 == 0:
            print(f"  [{i}s] {status}")
        if nCode == 0:  # Connected!
            print(f"  CONNECTED at {i}s!")
            break
    except Exception as e:
        if i == 0:
            print(f"  IsConnected error: {e}")
    time.sleep(1)
else:
    print("  Timeout - not connected after 30s")

# Try GetStockByNo anyway (might work without full connection)
print("\nTry GetStockByNoLONG('2344'):")
p = sk.SKSTOCKLONG()
r = m_pSKQuote.SKQuoteLib_GetStockByNoLONG("2344", p)
if isinstance(r, list):
    sd, nc = r[0], r[1]
    print(f"  nCode: {nc}")
    if nc == 0:
        print(f"  2344: open={sd.nOpen}, ref={sd.nRef}")
    else:
        print(f"  Error: {m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nc)}")

# Try GetBest5 (might work differently)
print("\nTry GetBest5LONG('2344'):")
try:
    p5 = sk.SKBEST5LONG()
    r = m_pSKQuote.SKQuoteLib_GetBest5LONG("2344", p5)
    print(f"  Result: {type(r)}")
    if isinstance(r, list):
        print(f"  nCode: {r[1]}")
except Exception as e:
    print(f"  Error: {e}")
