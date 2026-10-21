import sys, os, time
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
os.add_dll_directory(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
import comtypes.client
comtypes.client.GetModule(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll")
import comtypes.gen.SKCOMLib as sk

m_pSKCenter = comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
m_pSKQuote = comtypes.client.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)
m_pSKReply = comtypes.client.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)

class SKReplyEvent:
    def OnReplyMessage(self, bstrUserID, bstrMessages):
        return -1
reply_handler = comtypes.client.GetEvents(m_pSKReply, SKReplyEvent())

# Login
nCode = m_pSKCenter.SKCenterLib_Login("D121280815", "Zaq582811@")
if nCode != 0:
    print(f"Login failed: {m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)}")
    sys.exit(1)
print("Login OK")

# EnterMonitor
nCode = m_pSKQuote.SKQuoteLib_EnterMonitorLONG()
print(f"EnterMonitor: {'OK' if nCode == 0 else 'FAIL'}")

# Check available methods for requesting quotes
methods = [m for m in dir(m_pSKQuote) if 'Request' in m or 'Get' in m or 'Stock' in m]
print(f"\nAvailable quote methods ({len(methods)}):")
for m in sorted(methods):
    if 'Stock' in m or 'Request' in m:
        print(f"  {m}")

# Try RequestStockQuote for a specific stock
print("\n[Try] RequestStockByIndex for TWSE index 0:")
pSKStock = sk.SKSTOCKLONG()
try:
    pSKStock, nCode = m_pSKQuote.SKQuoteLib_GetStockByIndexLONG(0, 0, pSKStock)
    print(f"  nCode={nCode}, stock={pSKStock.bstrStockNo}, open={pSKStock.nOpen/100.0}")
except Exception as e:
    print(f"  Error: {e}")

# Try getting market total number
print("\n[Try] GetMarketTotNum:")
for method_name in ['SKQuoteLib_GetMarketTotNumLong', 'SKQuoteLib_GetMarketTotNumLONG']:
    try:
        fn = getattr(m_pSKQuote, method_name)
        result = fn(0)
        print(f"  {method_name}(0) = {result}")
        break
    except AttributeError:
        continue
    except Exception as e:
        print(f"  {method_name}: {e}")
        break

# Try RequestStockQuote
print("\n[Try] RequestStockQuote:")
for method_name in ['SKQuoteLib_RequestStockQuote', 'SKQuoteLib_RequestStocksByIndexRange']:
    try:
        fn = getattr(m_pSKQuote, method_name)
        print(f"  {method_name} exists!")
    except AttributeError:
        pass

# Check if there's a way to get stock list
print("\n[Try] GetStockByCode:")
pSKStock = sk.SKSTOCKLONG()
try:
    pSKStock, nCode = m_pSKQuote.SKQuoteLib_GetStockByCodeLONG(0, "2330", pSKStock)
    print(f"  2330: nCode={nCode}, open={pSKStock.nOpen/100.0}, ref={pSKStock.nRef/100.0}")
except Exception as e:
    print(f"  Error: {e}")

print("\nDone. (Market closed - no real-time data expected)")
