import requests, json, time, re

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 1. Try to find TWSE API by fetching their page and looking for API calls
print("=== TWSE Page Source Analysis ===")
try:
    r = requests.get("https://www.twse.com.tw/zh/page/trading/final/STOCK.html", headers=headers, timeout=10)
    print(f"TWSE page: {r.status_code} len={len(r.text)}")
    # Look for API URLs in the page
    api_patterns = re.findall(r'(https?://[^"\s]+(?:api|json|data|stock)[^"\s]*)', r.text, re.I)
    for p in api_patterns[:10]:
        print(f"  Found: {p}")
    # Also look for fetch/ajax calls
    fetch_patterns = re.findall(r'fetch\s*\(\s*["\']([^"\']+)["\']', r.text)
    ajax_patterns = re.findall(r'url\s*[:=]\s*["\']([^"\']+)["\']', r.text)
    for p in (fetch_patterns + ajax_patterns)[:10]:
        print(f"  AJAX: {p}")
except Exception as e:
    print(f"  Error: {e}")

# 2. Try TWSE known working endpoints (from their developer docs)
print("\n=== TWSE Direct API Attempts ===")
twse_attempts = [
    ("stockPrice JSON", "https://www.twse.com.tw/data/stockPrice", {"response": "json"}),
    ("stockPrice v2", "https://www.twse.com.tw/v2/stockPrice", {}),
    ("trade SAQ", "https://www.twse.com.tw/zh/api/trade/SAQ", {"response": "json"}),
    ("daily quote", "https://www.twse.com.tw/exchangeReport/STOCK_DAY", {"response": "json", "date": "20261020"}),
    ("intraday", "https://www.twse.com.tw/intraday/api/stockPrice", {}),
]
for name, url, params in twse_attempts:
    try:
        r = requests.get(url, headers=headers, params=params, timeout=8)
        is_json = r.status_code == 200 and r.text.strip()[:1] in "[{"
        print(f"  {name}: {r.status_code} json={is_json}")
        if is_json:
            data = r.json()
            if isinstance(data, list):
                print(f"    {len(data)} items")
            elif isinstance(data, dict):
                print(f"    keys: {list(data.keys())[:5]}")
    except Exception as e:
        print(f"  {name}: {str(e)[:60]}")

# 3. Try 群益 app API (their mobile app must have one)
print("\n=== Capital (群益) App API ===")
capital_attempts = [
    ("Capital stock list", "https://emoney.capital.com.tw/Api/Stock/GetStockList", {}),
    ("Capital quote", "https://emoney.capital.com.tw/Api/Stock/GetQuote", {"stockNo": "2330"}),
    ("Capital all quotes", "https://emoney.capital.com.tw/Api/Stock/GetAllQuote", {}),
]
for name, url, params in capital_attempts:
    try:
        r = requests.get(url, headers=headers, params=params, timeout=8)
        print(f"  {name}: {r.status_code} len={len(r.text)}")
        if r.status_code == 200 and r.text.strip()[:1] in "[{":
            print(f"    {r.text[:200]}")
    except Exception as e:
        print(f"  {name}: {str(e)[:60]}")

# 4. Try CMoney / other free APIs
print("\n=== Other Sources ===")
others = [
    ("CMoney", "https://cmapi.cmoney.tw/StockQuote/1.0/Quote/GetQuote", {"id": "2330"}),
    ("Rakuten", "https://rapi.rakuten.com.tw/stock/v1/quote/2330", {}),
]
for name, url, params in others:
    try:
        r = requests.get(url, headers=headers, params=params, timeout=8)
        print(f"  {name}: {r.status_code}")
        if r.status_code == 200:
            print(f"    {r.text[:200]}")
    except Exception as e:
        print(f"  {name}: {str(e)[:60]}")
