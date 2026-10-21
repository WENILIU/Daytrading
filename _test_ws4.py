from fugle_marketdata import WebSocketClient
import time

ws = WebSocketClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
stock_ws = ws.stock

# Try different event names
messages = []
def handler(*args, **kwargs):
    messages.append((args, kwargs))
    print(f"  MSG: args={args[:1]}, kwargs={list(kwargs.keys()) if kwargs else 'none'}")

# Register for multiple event types
for event_name in ['message', 'data', 'tick', 'quote', 'stock']:
    try:
        stock_ws.on(event_name, handler)
    except:
        pass

# Connect and subscribe
stock_ws.connect()
time.sleep(1)

# Try different subscribe formats
topics = [
    "realtime/quote/2330",
    "quote/2330", 
    "2330",
]
for t in topics:
    try:
        stock_ws.subscribe(t)
        print(f"  Sub: {t} OK")
    except Exception as e:
        print(f"  Sub: {t} - {e}")

time.sleep(5)

print(f"\nTotal messages: {len(messages)}")
if messages:
    print(f"First: {messages[0]}")

# Check auth status
print(f"\nAuth status: {stock_ws.auth_status}")
print(f"Subscriptions: {stock_ws.subscriptions}")

stock_ws.disconnect()
