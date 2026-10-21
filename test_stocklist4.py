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

for mk in [0]:
    SK.LoadCommodity(mk)
    r = SK.RequestStockList(mk)
    raw = r.RawData() if callable(r.RawData) else r.RawData
    if not raw:
        raw = r.raw_data() if callable(r.raw_data) else r.raw_data
    print(f"RawData type: {type(raw)}")
    print(f"RawData repr (first 500): {repr(raw)[:500]}")
    print(f"raw_data type: {type(r.raw_data)}")
    if callable(r.raw_data):
        rd = r.raw_data()
        print(f"raw_data() repr: {repr(rd)[:500]}")
    # Also check AllTypeLists
    atl = r.AllTypeLists
    print(f"AllTypeLists type: {type(atl)}")
    if callable(atl):
        a = atl()
        print(f"AllTypeLists() type: {type(a)}, len: {len(a) if hasattr(a,'__len__') else 'N/A'}")
        if a and len(a) > 0:
            print(f"  First: {repr(a[0])[:200]}")
