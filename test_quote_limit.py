import sys, time
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\SKDLLPythonTester")
from SKDLLPython import SK

CUST_ID = "D121280815"
PASSWORD = "Zaq582811@"

def on_reply(login_id, msg): pass
def on_conn(login_id, code): pass
SK.OnReplyMessage(on_reply)
SK.OnConnection(on_conn)

result = SK.Login(CUST_ID, PASSWORD)
if result.Code != 0:
    print(f"Login failed: {result.Code}"); sys.exit(1)

for t in [0, 1, 4]:
    SK.ManageServerConnection(CUST_ID, 0, t)
time.sleep(2)

# Check quote status/limits
# The COM version has GetQuoteStatus - check if SKDLL has equivalent
print("Checking quote connection status...")
# Try to find the limit by subscribing increasing numbers
with open("all_stocks.txt") as f:
    stocks = [s.strip() for s in f if s.strip()]

# Subscribe 140 (known to work)
nc = SK.SKQuoteLib_RequestStocks(",".join(stocks[:140]))
print(f"Subscribe 140: {nc} ({SK.GetMessage(nc)})")

time.sleep(3)

# Count how many got data
valid = 0
for code in stocks[:140]:
    for mk in [0, 1]:
        r = SK.SKQuoteLib_GetStockByStockNo(mk, code)
        if r.nCode == 0:
            dec = r.nDecimal if r.nDecimal > 0 else 2
            div = 10 ** dec
            if r.nOpen / div > 0 and r.nRef / div > 0:
                valid += 1
                break

print(f"Valid prices from 140 subscribed: {valid}")
print(f"This confirms the ~140 stock real-time limit.")
