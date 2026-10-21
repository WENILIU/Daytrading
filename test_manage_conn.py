import sys, os, time
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\SKDLLPythonTester")
os.add_dll_directory(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
from SKDLLPython import SK

CUST_ID = "D121280815"
PASSWORD = "Zaq582811@"

def on_reply(a, b): pass
def on_quote(market_no, stock_no, data):
    print(f"  >> QUOTE: {stock_no} open={data.nOpen} ref={data.nRef}")

SK.OnReplyMessage(on_reply)
SK.OnNotifyQuoteLONG(on_quote)

# Login
result = SK.Login(CUST_ID, PASSWORD)
print(f"Login: {result.Code}")

# Try ManageServerConnection with different target types
print("\nManageServerConnection attempts:")
for target in range(5):
    r = SK.ManageServerConnection(CUST_ID, 0, target)
    print(f"  target={target}: {r} - {SK.GetMessage(r)}")

# Wait
print("\nWaiting 3s...")
time.sleep(3)

# Try RequestStocks
print("\nRequestStocks('2330'):")
r = SK.SKQuoteLib_RequestStocks("2330")
print(f"  Result: {r} - {SK.GetMessage(r)}")

time.sleep(3)

# Read
print("\nGetStockByStockNo('2330'):")
data = SK.SKQuoteLib_GetStockByStockNo(0, "2330")
print(f"  nCode={data.nCode} nOpen={data.nOpen} nRef={data.nRef} nClose={data.nClose}")
