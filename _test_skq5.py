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
m_pSKQuote.SKQuoteLib_EnterMonitorLONG()
time.sleep(2)

# Method 1: RequestStockList for market 0 (上市)
print("RequestStockList(0):")
nCode = m_pSKQuote.SKQuoteLib_RequestStockList(0)
print(f"  Result: {m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)}")
time.sleep(2)

# Now try GetStockByIndex
print("\nGetStockByIndex after RequestStockList:")
count = 0
for i in range(100):
    p = sk.SKSTOCKLONG()
    r = m_pSKQuote.SKQuoteLib_GetStockByIndexLONG(0, i, p)
    if isinstance(r, list):
        sd, nc = r[0], r[1]
    elif isinstance(r, tuple):
        sd, nc = r
    else:
        break
    if nc != 0:
        if i == 0:
            print(f"  First error: code={nc}")
        break
    if i < 5:
        print(f"  [{i}] {sd.bstrStockNo}: open={sd.nOpen}, ref={sd.nRef}")
    count += 1
print(f"  Total: {count} stocks")

# Method 2: Subscribe specific stocks then get
print("\nSubscribe 2344 then get:")
psPageNo = ctypes.c_long(1)
nCode = m_pSKQuote.SKQuoteLib_RequestStocks(psPageNo, "2344")
print(f"  Subscribe: {m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)}")
time.sleep(1)

p = sk.SKSTOCKLONG()
r = m_pSKQuote.SKQuoteLib_GetStockByNoLONG("2344", p)
if isinstance(r, list):
    sd, nc = r[0], r[1]
else:
    sd, nc = r[0] if isinstance(r, tuple) else r, -1
print(f"  nCode: {nc}")
if nc == 0:
    print(f"  2344: open={sd.nOpen}, ref={sd.nRef}, close={sd.nClose}")
    # Prices are in cents (divide by 100 for 1-decimal stocks)
    print(f"  Actual: open={sd.nOpen/10:.1f}, ref={sd.nRef/10:.1f}")
