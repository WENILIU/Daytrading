from fugle_marketdata import WebSocketClient
import time

ws = WebSocketClient(api_key='MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==')
stock_ws = ws.stock

print("stock_ws type:", type(stock_ws))
print("stock_ws methods:", [x for x in dir(stock_ws) if not x.startswith('_')])

# Check realtime
if hasattr(stock_ws, 'realtime'):
    rt = stock_ws.realtime
    print(f"\nrealtime methods: {[x for x in dir(rt) if not x.startswith('_')]}")

# Check quote
if hasattr(stock_ws, 'quote'):
    q = stock_ws.quote
    print(f"\nquote methods: {[x for x in dir(q) if not x.startswith('_')]}")

# Check tick
if hasattr(stock_ws, 'tick'):
    t = stock_ws.tick
    print(f"\ntick methods: {[x for x in dir(t) if not x.startswith('_')]}")
