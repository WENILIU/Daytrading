import comtypes.client
import ctypes

comtypes.client.GetModule(r'D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll')
import comtypes.gen.SKCOMLib as sk

# Find all struct-like types
structs = [x for x in dir(sk) if x.startswith('tag') or x.startswith('tag')]
print("tag structs:", structs[:30])

# Look for SKStock
sk_items = [x for x in dir(sk) if 'SK' in x and not x.startswith('ISK') and not x.startswith('_')]
print("\nSK items:", sk_items[:30])

# Try calling GetStockByNoLONG directly
m_pSKCenter = comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
m_pSKReply = comtypes.client.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)
m_pSKQuote = comtypes.client.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)

class RE:
    def OnReplyMessage(self, a, b): return -1
h = comtypes.client.GetEvents(m_pSKReply, RE())
m_pSKCenter.SKCenterLib_SetAuthority(0)
m_pSKCenter.SKCenterLib_Login('D121280815', 'Zaq582811@')
m_pSKQuote.SKQuoteLib_EnterMonitorLONG()
import time; time.sleep(2)

# Try calling with different approaches
print("\nTrying GetStockByNoLONG...")
try:
    # The function signature might need a pointer
    result = m_pSKQuote.SKQuoteLib_GetStockByNoLONG('2344')
    print(f"  Direct call result: {type(result)}")
    if hasattr(result, 'nOpen'):
        print(f"  nOpen: {result.nOpen}")
    elif isinstance(result, tuple):
        print(f"  Tuple: {result}")
except Exception as e:
    print(f"  Error: {e}")

# Try with ctypes pointer
try:
    buf = ctypes.create_string_buffer(1024)
    result = m_pSKQuote.SKQuoteLib_GetStockByNoLONG('2344', buf)
    print(f"  With buffer: {result}")
except Exception as e:
    print(f"  Buffer error: {e}")
