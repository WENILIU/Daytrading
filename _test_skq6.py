import comtypes.client
import ctypes
import time
import threading

comtypes.client.GetModule(r'D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll')
import comtypes.gen.SKCOMLib as sk

m_pSKCenter = comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
m_pSKReply = comtypes.client.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)
m_pSKQuote = comtypes.client.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)

# Track connection status
connected = threading.Event()

class QuoteEvent:
    def OnConnection(self, nKind, nCode):
        print(f"  [Quote OnConnection] kind={nKind}, code={nCode}")
        if nCode == 0:
            connected.set()

class RE:
    def OnReplyMessage(self, a, b): return -1

h1 = comtypes.client.GetEvents(m_pSKReply, RE())
h2 = comtypes.client.GetEvents(m_pSKQuote, QuoteEvent())

m_pSKCenter.SKCenterLib_SetAuthority(0)
nCode = m_pSKCenter.SKCenterLib_Login('D121280815', 'Zaq582811@')
print(f"Login: {m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)}")

# Enter monitor - this starts the quote connection
print("EnterMonitor...")
nCode = m_pSKQuote.SKQuoteLib_EnterMonitorLONG()
print(f"  Result: {m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)}")

# Wait for connection (max 15s)
print("Waiting for quote connection...")
got_connection = connected.wait(timeout=15)
print(f"  Connected: {got_connection}")

if not got_connection:
    # Try anyway after 5s
    time.sleep(5)

# Now try RequestStockList
print("\nRequestStockList(0) - 上市:")
nCode = m_pSKQuote.SKQuoteLib_RequestStockList(0)
print(f"  Result: {m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)}")
time.sleep(3)

# Try GetStockByIndex
print("\nGetStockByIndex(0, 0..5):")
for i in range(6):
    p = sk.SKSTOCKLONG()
    r = m_pSKQuote.SKQuoteLib_GetStockByIndexLONG(0, i, p)
    if isinstance(r, list):
        sd, nc = r[0], r[1]
    elif isinstance(r, tuple):
        sd, nc = r
    else:
        print(f"  Unexpected: {type(r)}")
        break
    if nc != 0:
        print(f"  [{i}] error code={nc}")
        break
    print(f"  [{i}] {sd.bstrStockNo} {sd.bstrStockName}: open={sd.nOpen}, ref={sd.nRef}")
