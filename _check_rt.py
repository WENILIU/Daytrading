import sys, io, time, json, requests, urllib3
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
urllib3.disable_warnings()

now = datetime.now()
print(f"Current time: {now}")
print("=" * 60)

# ============================================================
# TEST 1: TWSE with verify=False and proper headers
# ============================================================
print("\n=== TWSE (verify=False) ===")
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.twse.com.tw/zh/page/trading/realtime/STOCK.html",
}
# Try the actual stock quote endpoint
for path in [
    "https://www.twse.com.tw/zh/api/trade/stock/2330",
    "https://www.twse.com.tw/api/trade/stock/2330",
    "https://www.twse.com.tw/zh/api/trade/stock/all",
]:
    try:
        r = requests.get(path, timeout=5, headers=headers, verify=False)
        ct = r.headers.get("content-type", "")
        print(f"  {r.status_code} | {ct[:30]:30} | {len(r.text):>6}b | {path[-30:]}")
        if r.status_code == 200 and "json" in ct:
            d = r.json()
            print(f"    -> {list(d.keys())[:5]}")
    except Exception as e:
        print(f"  ERR | {path[-30:]} | {str(e)[:40]}")

# ============================================================
# TEST 2: TPEx (上櫃) real-time
# ============================================================
print("\n=== TPEx ===")
tpex_urls = [
    "https://www.tpex.org.tw/web/stock/3310r04/daily?l=zh-tw&ot=1900",
    "https://www.tpex.org.tw/web/stock/info/realtime?l=zh-tw",
]
for url in tpex_urls:
    try:
        r = requests.get(url, timeout=5, headers=headers, verify=False)
        ct = r.headers.get("content-type", "")
        print(f"  {r.status_code} | {ct[:30]:30} | {len(r.text):>6}b | {url[-40:]}")
        if "json" in ct and r.status_code == 200:
            d = r.json()
            if "data" in d:
                print(f"    -> {len(d['data'])} records")
    except Exception as e:
        print(f"  ERR | {url[-40:]} | {str(e)[:40]}")

# ============================================================
# TEST 3: Google Finance (verify=False)
# ============================================================
print("\n=== Google Finance ===")
try:
    url = "https://www.google.com/finance/quote/2330:TPE"
    r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}, verify=False)
    print(f"  Status: {r.status_code}, Size: {len(r.text)}")
    # Try to extract price from HTML
    import re
    match = re.search(r'data-last-price="([\d.]+)"', r.text)
    if match:
        print(f"  Price found: {match.group(1)}")
    else:
        # Try other patterns
        match2 = re.search(r'"2330"[^}]*"price"[^}]*([\d.]+)', r.text)
        if match2:
            print(f"  Price (alt): {match2.group(1)}")
        else:
            print(f"  Could not extract price from HTML")
except Exception as e:
    print(f"  Error: {str(e)[:80]}")

# ============================================================
# TEST 4: 群益 web trading API (try different domains)
# ============================================================
print("\n=== Capital Securities (try more) ===")
cap_urls = [
    "https://jwsk.capital.com.tw/api/quote/realtime?symbol=2330",
    "https://skcap.capital.com.tw/api/quote/realtime?symbol=2330",
    "https://m.capital.com.tw/api/quote/realtime?symbol=2330",
    "https://api.capital.com.tw/quote/realtime?symbol=2330",
]
for url in cap_urls:
    try:
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"}, verify=False)
        print(f"  {r.status_code} | {len(r.text):>6}b | {url[:55]}")
    except Exception as e:
        print(f"  ERR | {url[:55]} | {str(e)[:40]}")

# ============================================================
# TEST 5: Fugle timing test (how fast can we scan?)
# ============================================================
print("\n=== Fugle speed test (20 stocks) ===")
from fugle_marketdata import RestClient
from concurrent.futures import ThreadPoolExecutor, as_completed

client = RestClient(api_key="MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw==")
stock = client.stock

test_codes = ["2330","2454","2344","2317","2303","6505","3711","2412","2308","2311",
              "2312","2313","2316","2323","2324","2327","2328","2329","2331","2332"]

def fetch(sym):
    try:
        q = stock.intraday.quote(symbol=sym)
        return {"sym": sym, "price": q.get("lastPrice"), "time": q.get("lastTrade",{}).get("time")}
    except:
        return None

t0 = time.time()
results = []
with ThreadPoolExecutor(max_workers=10) as ex:
    futures = [ex.submit(fetch, s) for s in test_codes]
    for f in as_completed(futures):
        r = f.result()
        if r:
            results.append(r)
elapsed = time.time() - t0

print(f"  20 stocks in {elapsed:.2f}s, got {len(results)}")
if results:
    # Check freshness
    sample = results[0]
    ts_us = sample.get("time", 0)
    if ts_us:
        trade_time = datetime.fromtimestamp(ts_us / 1_000_000)
        delay = (now - trade_time).total_seconds()
        print(f"  Sample trade time: {trade_time}")
        print(f"  Delay: {delay:.1f}s")
