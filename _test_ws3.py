from fugle_marketdata import WebSocketClient
import time
import threading

ws = WebSocketClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
stock_ws = ws.stock

# Collect received data
received = {}
def on_message(event):
    # event might have topic and data
    topic = event.get('topic', '') if isinstance(event, dict) else getattr(event, 'topic', '')
    data = event.get('payload', event.get('data', {})) if isinstance(event, dict) else getattr(event, 'payload', {})
    if topic:
        received[topic] = data

# Register handler
stock_ws.on('message', on_message)

# Connect
print("Connecting...")
stock_ws.connect()
time.sleep(2)

# Subscribe to a few stocks (realtime quote)
test_symbols = ['2330', '2454', '2344']
for sym in test_symbols:
    topic = f"realtime/quote/{sym}"
    stock_ws.subscribe(topic)
    print(f"  Subscribed: {topic}")

# Wait for data
print("Waiting 5s for data...")
time.sleep(5)

print(f"\nReceived {len(received)} topics:")
for topic, data in list(received.items())[:3]:
    print(f"  {topic}: {data}")

# Check if we can subscribe to all
print("\nTrying wildcard/all subscription...")
try:
    stock_ws.subscribe("realtime/quote/*")
    print("  Wildcard subscribed")
except Exception as e:
    print(f"  Wildcard error: {e}")

stock_ws.disconnect()
