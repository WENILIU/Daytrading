import requests, json, time
from datetime import datetime

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Test 1: Yahoo batch quote (v7 endpoint - supports multiple symbols)
print("=== Yahoo Batch Quote Test ===")
symbols = ["2330.TW", "2454.TW", "2317.TW", "2303.TW", "6505.TW"]
url = "https://query1.finance.yahoo.com/v7/finance/quote"
params = {"symbols": ",".join(symbols)}

r = requests.get(url, headers=headers, params=params, timeout=10)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    results = data.get("quoteResponse", {}).get("result", [])
    print(f"Got {len(results)} quotes")
    for q in results:
        sym = q.get("symbol", "")
        price = q.get("regularMarketPrice", 0)
        prev = q.get("regularMarketPreviousClose", 0)
        open_p = q.get("regularMarketOpen", 0)
        ts = q.get("regularMarketTime", 0)
        update_time = datetime.fromtimestamp(ts) if ts else "N/A"
        gap = (open_p - prev) / prev * 100 if prev and open_p else 0
        print(f"  {sym}: price={price} open={open_p} prev={prev} gap={gap:+.1f}% updated={update_time}")
else:
    print(f"  Error: {r.text[:300]}")

# Test 2: Check actual delay by querying twice
print("\n=== Delay Test (2 queries, 5s apart) ===")
r1 = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers=headers, timeout=10)
if r1.status_code == 200:
    meta1 = r1.json()["chart"]["result"][0]["meta"]
    t1 = meta1.get("regularMarketTime", 0)
    p1 = meta1.get("regularMarketPrice", 0)
    print(f"  t1={datetime.fromtimestamp(t1)} price={p1}")

time.sleep(5)

r2 = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/2330.TW", headers=headers, timeout=10)
if r2.status_code == 200:
    meta2 = r2.json()["chart"]["result"][0]["meta"]
    t2 = meta2.get("regularMarketTime", 0)
    p2 = meta2.get("regularMarketPrice", 0)
    print(f"  t2={datetime.fromtimestamp(t2)} price={p2}")
    print(f"  Now: {datetime.now()}")
    if t2 > t1:
        print("  => DATA UPDATES IN REAL-TIME!")
    else:
        print("  => Same timestamp (possibly cached/delayed)")

# Test 3: How many symbols can we batch?
print("\n=== Batch Size Test ===")
for n in [50, 100, 200]:
    syms = [f"{2300+i}.TW" for i in range(n)]
    url = "https://query1.finance.yahoo.com/v7/finance/quote"
    params = {"symbols": ",".join(syms)}
    t0 = time.time()
    r = requests.get(url, headers=headers, params=params, timeout=15)
    elapsed = time.time() - t0
    if r.status_code == 200:
        results = r.json().get("quoteResponse", {}).get("result", [])
        print(f"  {n} symbols: {len(results)} results in {elapsed:.1f}s")
    else:
        print(f"  {n} symbols: HTTP {r.status_code} in {elapsed:.1f}s")
    time.sleep(1)
