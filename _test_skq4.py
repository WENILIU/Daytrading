import comtypes.client
import time

comtypes.client.GetModule(r'D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll')
import comtypes.gen.SKCOMLib as sk

# Check SKSTOCKLONG fields
fields = [x for x in dir(sk.SKSTOCKLONG) if not x.startswith('_')]
print("SKSTOCKLONG fields:", fields)

# Connect
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

# Get stock 2344
print("\nGetStockByNoLONG('2344'):")
p = sk.SKSTOCKLONG()
result = m_pSKQuote.SKQuoteLib_GetStockByNoLONG('2344', p)
print(f"  Return type: {type(result)}")
if isinstance(result, tuple):
    stock_data, nCode = result
    print(f"  nCode: {nCode}")
    print(f"  bstrCode: {stock_data.bstrCode}")
    print(f"  nOpen: {stock_data.nOpen}")
    print(f"  nRef: {stock_data.nRef}")
    print(f"  nClose: {stock_data.nClose}")
    print(f"  nLow: {stock_data.nLow}")
    print(f"  nHigh: {stock_data.nHigh}")
else:
    print(f"  Result: {result}")

# Try iterating all stocks by index
print("\nIterating market 0 (上市) by index:")
start = time.time()
count = 0
for i in range(50):
    p2 = sk.SKSTOCKLONG()
    r = m_pSKQuote.SKQuoteLib_GetStockByIndexLONG(0, i, p2)
    if isinstance(r, tuple):
        sd, nc = r
        if nc != 0:
            break
        if i < 5:
            print(f"  [{i}] {sd.bstrCode}: open={sd.nOpen}, ref={sd.nRef}")
        count += 1
    else:
        break
elapsed = time.time() - start
print(f"  Got {count} stocks in {elapsed:.2f}s")
