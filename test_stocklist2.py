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

# Get stock list
for mk in [0, 1]:
    SK.LoadCommodity(mk)
    r = SK.RequestStockList(mk)
    raw = r.RawData
    if raw:
        lines = raw.split("\n")
        print(f"Market {mk}: {len(lines)} lines")
        # Parse stock codes from raw data
        codes = []
        for line in lines:
            parts = line.split(",")
            if len(parts) >= 2:
                code = parts[0].strip()
                if code and code[0].isdigit():
                    codes.append(code)
        print(f"  Parsed {len(codes)} stock codes")
        if codes:
            print(f"  Sample: {codes[:10]}")
            # Save to file
            with open(f"valid_stocks_{mk}.txt", "w") as f:
                f.write("\n".join(codes))
    else:
        print(f"Market {mk}: no raw data")
        # Try AllTypeLists
        atl = r.AllTypeLists
        print(f"  AllTypeLists type: {type(atl)}")
        if atl:
            print(f"  First entry: {atl[0] if len(atl) > 0 else 'empty'}")
