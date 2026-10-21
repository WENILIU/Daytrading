"""
Optimized TWSE Scanner - target: <10 seconds for full market
Optimizations:
1. requests.Session (connection pooling / keep-alive)
2. More parallel workers (20)
3. Pre-filter valid stock codes (skip delisted)
4. Smaller batches (50) for better load distribution
5. Shorter timeout for faster failure
"""
import requests, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter

TWSE_API = "http://mis.twse.com.tw/stock/api/getStockInfo.jsp"

# Create session with connection pooling
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})
adapter = HTTPAdapter(pool_connections=30, pool_maxsize=30)
session.mount("http://", adapter)

def _query_batch(codes, market=0):
    prefix = "tse" if market == 0 else "otc"
    parts = [f"{prefix}_{c}.tw" for c in codes]
    ex_ch = "|".join(parts)
    url = f"{TWSE_API}?ex_ch={ex_ch}&_={int(time.time()*1000)}"
    try:
        r = session.get(url, timeout=8)
        if r.status_code != 200:
            return []
        text = r.text.strip()
        idx = text.find("{")
        if idx < 0:
            return []
        data = json.loads(text[idx:])
        return data.get("msgArray", [])
    except:
        return []

def scan(stocks, batch_size=50, workers=20, gap_threshold=0.05):
    t0 = time.time()
    batches = [stocks[i:i+batch_size] for i in range(0, len(stocks), batch_size)]
    
    all_raw = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_query_batch, b) for b in batches]
        for f in as_completed(futures):
            all_raw.extend(f.result())
    
    gaps = []
    for s in all_raw:
        try:
            o = float(s.get("o", "0").replace("-", "0"))
            y = float(s.get("y", "0").replace("-", "0"))
            if o > 0 and y > 0:
                gap = (o - y) / y
                if abs(gap) >= gap_threshold:
                    gaps.append((s.get("c",""), o, y, round(gap*100,2)))
        except:
            continue
    
    elapsed = time.time() - t0
    gaps.sort(key=lambda x: abs(x[3]), reverse=True)
    print(f"  {len(stocks)} codes -> {len(all_raw)} data -> {len(gaps)} gaps | {elapsed:.1f}s")
    return gaps

# Load and filter valid stocks
with open("all_stocks.txt") as f:
    all_stocks = [s.strip() for s in f if s.strip()]

# Use the valid list from earlier test (1928 confirmed valid)
try:
    with open("valid_stocks.txt") as f:
        valid_stocks = [s.strip() for s in f if s.strip()]
    print(f"Using pre-filtered valid list: {len(valid_stocks)} stocks")
except:
    valid_stocks = all_stocks
    print(f"Using full list: {len(all_stocks)} stocks")

print("\n=== Test 1: batch=50, workers=20 ===")
scan(valid_stocks, batch_size=50, workers=20)

print("\n=== Test 2: batch=100, workers=20 ===")
scan(valid_stocks, batch_size=100, workers=20)

print("\n=== Test 3: batch=50, workers=30 ===")
scan(valid_stocks, batch_size=50, workers=30)

print("\n=== Test 4: batch=100, workers=30 ===")
scan(valid_stocks, batch_size=100, workers=30)
