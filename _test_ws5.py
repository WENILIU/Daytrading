from fugle_marketdata import WebSocketClient
import time
import json

ws = WebSocketClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
stock_ws = ws.stock

messages = []
def handler(*args, **kwargs):
    if args and isinstance(args[0], str):
        try:
            parsed = json.loads(args[0])
            messages.append(parsed)
            if parsed.get('event') != 'authenticated':
                print(f"  {parsed.get('event')}: {str(parsed)[:150]}")
        except:
            messages.append(args[0])

stock_ws.on('message', handler)
stock_ws.connect()
time.sleep(2)

# Check the subscribe method source
import inspect
try:
    src = inspect.getsource(stock_ws.subscribe)
    print("subscribe source:")
    print(src[:500])
except:
    pass

# Try correct format based on Fugle docs
# Format should be: {"channel": "realtime.quote", "symbols": ["2330"]}
# Or the subscribe method might take specific params
print("\nTrying subscribe with dict:")
try:
    stock_ws.subscribe({"channel": "realtime.quote", "symbols": ["2330", "2454"]})
    print("  dict subscribe OK")
except Exception as e:
    print(f"  dict error: {e}")

time.sleep(5)

print(f"\nMessages: {len(messages)}")
for m in messages:
    if isinstance(m, dict) and m.get('event') not in ('authenticated',):
        print(f"  {json.dumps(m, ensure_ascii=False)[:200]}")

stock_ws.disconnect()
