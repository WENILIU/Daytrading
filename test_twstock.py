import twstock
import time

# twstock can get real-time data
print("=== twstock Real-time Test ===")

# Get real-time status for a stock
t0 = time.time()
try:
    stock = twstock.realtime.get("2330")
    elapsed = time.time() - t0
    print(f"2330 realtime ({elapsed:.2f}s):")
    if stock.success:
        info = stock.info
        print(f"  open={info.get('open')} high={info.get('high')} low={info.get('low')} close={info.get('close')}")
        print(f"  yesterday={info.get('yesterdayClose')}")
        print(f"  volume={info.get('volume')}")
        print(f"  all keys: {list(info.keys())[:15]}")
    else:
        print(f"  Failed: {stock.message}")
except Exception as e:
    print(f"  Error: {e}")

# Try getting all stocks
print("\n=== All Stocks ===")
t0 = time.time()
try:
    # twstock has a function to get all stock codes
    codes = twstock.codes
    print(f"Available codes: {len(codes)}")
    # Get first few
    sample = list(codes.keys())[:5]
    print(f"Sample: {sample}")
except Exception as e:
    print(f"codes error: {e}")

# Try batch realtime
print("\n=== Batch Realtime ===")
t0 = time.time()
try:
    # twstock.realtime can take multiple stocks
    stocks = twstock.realtime.get(["2330", "2454", "2317", "2303", "6505"])
    elapsed = time.time() - t0
    print(f"Batch 5 stocks ({elapsed:.2f}s):")
    if isinstance(stocks, list):
        for s in stocks:
            if s.success:
                info = s.info
                print(f"  {s.stock_id}: open={info.get('open')} prev={info.get('yesterdayClose')}")
    elif hasattr(stocks, 'success') and stocks.success:
        info = stocks.info
        print(f"  {info}")
except Exception as e:
    print(f"  Error: {e}")
