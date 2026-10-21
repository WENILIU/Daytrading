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

for mk in [0, 1]:
    SK.LoadCommodity(mk)
    r = SK.RequestStockList(mk)
    # RawData is a method
    raw = r.RawData() if callable(r.RawData) else r.RawData
    if not raw:
        raw = r.raw_data() if callable(r.raw_data) else r.raw_data
    if raw:
        lines = raw.split("\n")
        print(f"Market {mk}: {len(lines)} lines")
        codes = []
        for line in lines:
            parts = line.split(",")
            if len(parts) >= 2:
                code = parts[0].strip()
                if code and code[0].isdigit():
                    codes.append(code)
        print(f"  Parsed {len(codes)} codes")
        if codes:
            print(f"  Sample: {codes[:5]}")
            with open(f"valid_stocks_{mk}.txt", "w") as f:
                f.write("\n".join(codes))
    else:
        # Try GetAllType
        try:
            types = r.GetAllType()
            print(f"Market {mk}: GetAllType returned {type(types)}")
        except Exception as e:
            print(f"Market {mk}: error {e}")
