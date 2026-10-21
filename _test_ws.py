from fugle_marketdata import WebSocketClient
import time
import threading

# Check WebSocket API
print("WebSocketClient methods:", [x for x in dir(WebSocketClient) if not x.startswith('_')])

# Try to create and use it
ws = WebSocketClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
print(f"\nWS instance: {type(ws)}")
print(f"WS methods: {[x for x in dir(ws) if not x.startswith('_')]}")

# Check help
help(ws)
