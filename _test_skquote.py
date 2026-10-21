import comtypes.client
import time

comtypes.client.GetModule(r'D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll')
import comtypes.gen.SKCOMLib as sk

# Check tagSKStockLONG fields
fields = [x for x in dir(sk.tagSKStockLONG) if not x.startswith('_')]
print("tagSKStockLONG fields:", fields)

# Try to get stock data
m_pSKCenter = comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
m_pSKReply = comtypes.client.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)
m_pSKQuote = comtypes.client.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)

class ReplyEvent:
    def OnReplyMessage(self, bstrUserID, bstrMessages):
        return -1

handler = comtypes.client.GetEvents(m_pSKReply, ReplyEvent())
m_pSKCenter.SKCenterLib_SetAuthority(0)
nCode = m_pSKCenter.SKCenterLib_Login('D121280815', 'Zaq582811@')
print(f"\nLogin: {m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)}")

# Enter monitor
nCode = m_pSKQuote.SKQuoteLib_EnterMonitorLONG()
print(f"EnterMonitor: {m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)}")
time.sleep(2)

# Try GetStockByNo for 2344
pSKStock = sk.tagSKStockLONG()
pSKStock, nCode = m_pSKQuote.SKQuoteLib_GetStockByNoLONG('2344', pSKStock)
print(f"\n2344 quote: code={nCode}")
print(f"  nOpen: {pSKStock.nOpen}")
print(f"  nClose: {pSKStock.nClose}")
print(f"  nRef: {pSKStock.nRef}")
print(f"  nLow: {pSKStock.nLow}")
print(f"  nHigh: {pSKStock.nHigh}")

# Try iterating by index (market 0=上市)
print("\nTrying GetStockByIndex (上市 market=0):")
count = 0
for i in range(10):
    p = sk.tagSKStockLONG()
    p, nc = m_pSKQuote.SKQuoteLib_GetStockByIndexLONG(0, i, p)
    if nc != 0:
        break
    print(f"  [{i}] {p.bstrCode}: open={p.nOpen}, ref={p.nRef}, close={p.nClose}")
    count += 1

print(f"Got {count} stocks from index")
