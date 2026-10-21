"""Test quote via SKDLL (ctypes, no COM events)"""
import sys, os, time
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\SKDLLPythonTester")
os.add_dll_directory(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")

from SKDLLPython import SK

CUST_ID = "D121280815"
PASSWORD = "Zaq582811@"

quote_count = [0]

def on_reply(login_id, message):
    pass  # Required first!

def on_quote(market_no, stock_no, data):
    quote_count[0] += 1
    if quote_count[0] <= 5:
        print(f"  >> Quote: {stock_no} open={data.nOpen} ref={data.nRef}")

print("=" * 60)
print("SKDLL Quote Test v2")
print("=" * 60)

# 0. Register ReplyMessage FIRST (required before login)
print("\n[0] Register OnReplyMessage...")
SK.OnReplyMessage(on_reply)
print("  OK")

# 1. Register quote callback
print("[1] Register OnNotifyQuoteLONG...")
SK.OnNotifyQuoteLONG(on_quote)
print("  OK")

# 2. Login
print("\n[2] Login...")
result = SK.Login(CUST_ID, PASSWORD)
print(f"  Code: {result.Code} - {SK.GetMessage(result.Code)}")
if result.Code != 0:
    sys.exit(1)

# 3. Request stock list
print("\n[3] RequestStockList...")
try:
    sl = SK.RequestStockList(0)
    print(f"  Market 0: {len(sl.Items)} stocks")
except Exception as e:
    print(f"  Error: {e}")

# 4. Subscribe to stocks
print("\n[4] RequestStocks...")
try:
    nCode = SK.SKQuoteLib_RequestStocks("2330,2454,2317")
    print(f"  Code: {nCode}")
except Exception as e:
    print(f"  Error: {e}")

# 5. Wait for callbacks
print("\n[5] Waiting 5s...")
for i in range(50):
    time.sleep(0.1)
print(f"  Quotes received: {quote_count[0]}")

# 6. Read data
print("\n[6] GetStockByStockNo...")
for code in ["2330", "2454", "2317"]:
    try:
        data = SK.SKQuoteLib_GetStockByStockNo(0, code)
        print(f"  {code}: code={data.Code} open={data.nOpen} ref={data.nRef}")
    except Exception as e:
        print(f"  {code}: Error: {e}")

print(f"\nTotal callbacks: {quote_count[0]}")
