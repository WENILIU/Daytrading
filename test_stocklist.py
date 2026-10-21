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
print("[1] Login OK")

for t in [0, 1, 4]:
    SK.ManageServerConnection(CUST_ID, 0, t)
print("[2] Connected")
time.sleep(2)

# Get valid stock list
print("[3] RequestStockList...")
for mk in [0, 1]:
    SK.LoadCommodity(mk)
    r = SK.RequestStockList(mk)
    attrs = [a for a in dir(r) if not a.startswith("_")]
    print(f"  Market {mk}: type={type(r).__name__}")
    print(f"  attrs: {attrs}")
    # Try to get stock codes
    if hasattr(r, "StockList"):
        print(f"  StockList: {len(r.StockList)} items")
        if r.StockList:
            print(f"  First: {r.StockList[0]}")
    if hasattr(r, "Raw"):
        raw = r.Raw
        if raw:
            lines = raw.split("\n")
            print(f"  Raw: {len(lines)} lines")
            if lines:
                print(f"  Line0: {lines[0][:120]}")
                if len(lines) > 1:
                    print(f"  Line1: {lines[1][:120]}")
    break
