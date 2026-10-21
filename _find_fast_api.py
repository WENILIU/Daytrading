import urllib.request
import json
import time

# Option 1: TWSE real-time tick data (all stocks in one call)
print("=== TWSE stock_json ===")
try:
    url = "http://140.112.29.14:80/stock_json/"
    start = time.time()
    req = urllib.request.urlopen(url, timeout=10)
    data = json.loads(req.read().decode('utf-8'))
    elapsed = time.time() - start
    print(f"  Time: {elapsed:.2f}s")
    if isinstance(data, dict):
        print(f"  Keys: {list(data.keys())[:5]}")
        # Check structure
        for k in list(data.keys())[:2]:
            v = data[k]
            if isinstance(v, dict):
                print(f"  {k}: {list(v.keys())[:10]}")
                break
    elif isinstance(data, list):
        print(f"  Items: {len(data)}")
        if data:
            print(f"  First: {data[0]}")
except Exception as e:
    print(f"  Error: {e}")

# Option 2: TWSE query API
print("\n=== TWSE query (otex) ===")
try:
    url = "https://twse-webquery.twse.com.tw/common/stock/"
    req = urllib.request.urlopen(url, timeout=10)
    data = json.loads(req.read().decode('utf-8'))
    print(f"  Keys: {list(data.keys())[:5]}")
except Exception as e:
    print(f"  Error: {e}")

# Option 3: TPEx (上櫃) real-time
print("\n=== TPEx real-time ===")
try:
    url = "https://www.tpex.org.tw/web/stock/aftertrading/stockinfo/bd.php?l=zh-tw&s=0,asc,0"
    req = urllib.request.urlopen(url, timeout=10)
    data = json.loads(req.read().decode('utf-8'))
    print(f"  Keys: {list(data.keys())[:5]}")
    if 'data' in data:
        print(f"  Items: {len(data['data'])}")
        if data['data']:
            print(f"  First: {data['data'][0]}")
except Exception as e:
    print(f"  Error: {e}")

# Option 4: GoodInfo / 股市爆料
print("\n=== GoodInfo API ===")
try:
    url = "https://goodinfo.tw/tw/api/StockSocreApi.ashx?STOCK_ID=2330"
    req = urllib.request.urlopen(url, timeout=5)
    print(f"  OK: {req.read()[:100]}")
except Exception as e:
    print(f"  Error: {e}")
