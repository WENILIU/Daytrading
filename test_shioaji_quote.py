import shioaji as sj
import time

api = sj.Shioaji()
api.connect(
    api_key="D121280815",
    secret_key="Zaq582811@",
    ca_path=r"D:\CA\D121280815.capitalwebca"
)
print("[1] Connected")

# Check quote method signature
import inspect
print(f"[2] quote signature: {inspect.signature(api.quote)}")
print(f"[3] ticks signature: {inspect.signature(api.ticks)}")

# Try getting current quote for 2330
try:
    q = api.quote("2330")
    print(f"[4] quote('2330'): {q}")
except Exception as e:
    print(f"[4] quote error: {e}")

# Try the callback approach
quotes_received = []
def on_quote_callback(quote):
    quotes_received.append(quote)

api.set_on_quote_stk_v1_callback(on_quote_callback)
print("[5] Callback registered")

# Subscribe to some stocks
try:
    api.ticks("2330")
    print("[6] ticks('2330') OK")
except Exception as e:
    print(f"[6] ticks error: {e}")

time.sleep(3)
print(f"[7] Quotes received: {len(quotes_received)}")
if quotes_received:
    q = quotes_received[0]
    print(f"  Type: {type(q)}")
    print(f"  Attrs: {[a for a in dir(q) if not a.startswith('_')][:20]}")

api.close()
