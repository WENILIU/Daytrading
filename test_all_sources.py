import requests, json, time

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def test_api(name, url, params=None, method="GET"):
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, params=params, timeout=8)
        else:
            r = requests.post(url, headers=headers, data=params, timeout=8)
        ct = r.headers.get("content-type", "")
        is_json = r.status_code == 200 and ("json" in ct or r.text.strip()[:1] in "[{")
        print(f"{name}: {r.status_code} json={is_json} len={len(r.text)}")
        if is_json:
            data = r.json()
            if isinstance(data, list) and data:
                print(f"  ITEMS: {len(data)}")
                print(f"  SAMPLE: {str(data[0])[:200]}")
            elif isinstance(data, dict):
                keys = list(data.keys())[:8]
                print(f"  KEYS: {keys}")
                for k in keys:
                    v = data[k]
                    if isinstance(v, list) and v:
                        print(f"  {k}: {len(v)} items, sample: {str(v[0])[:150]}")
                        break
        return r
    except Exception as e:
        print(f"{name}: ERROR {str(e)[:80]}")
        return None

print("=" * 60)
print("TESTING ALL STOCK DATA SOURCES")
print("=" * 60)

# 1. TWSE
print("\n--- TWSE (證交所) ---")
test_api("TWSE trade SAQ", "https://www.twse.com.tw/zh/api/trade/SAQ")
test_api("TWSE stockPrice", "https://www.twse.com.tw/data/stockPrice")
test_api("TWSE en stockPrices", "https://www.twse.com.tw/en/api/stockPrices")

# 2. TPEX (櫃買)
print("\n--- TPEX (櫃買中心) ---")
test_api("TPEX b40", "https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_statistics/b40.php",
         {"l": "zh-tw", "s": "-1"})

# 3. GoodInfo
print("\n--- GoodInfo (好訊) ---")
test_api("GoodInfo stock", "https://goodinfo.tw/tw/StockBq/GetStockBq",
         {"StockId": "2330"})

# 4. Fugle (correct v2 paths)
print("\n--- Fugle (富果) ---")
FUGLE_KEY = "MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw=="
fh = {"Authorization": f"Bearer {FUGLE_KEY}"}
for path in ["/realtime/v2/intraday/quotes", "/marketdata/v2/intraday/quotes",
             "/realtime/v2/quotes", "/marketdata/v2/realtime/quotes"]:
    try:
        r = requests.get(f"https://api.fugle.tw{path}", headers=fh, params={"symbolId": "2330"}, timeout=8)
        print(f"Fugle {path}: {r.status_code}")
        if r.status_code == 200:
            print(f"  {r.text[:200]}")
    except: pass

# 5. Yahoo (check actual delay)
print("\n--- Yahoo Finance ---")
try:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/2330.TW"
    r = requests.get(url, headers=headers, timeout=8)
    if r.status_code == 200:
        data = r.json()
        meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
        print(f"  regularMarketPrice: {meta.get('regularMarketPrice')}")
        print(f"  previousClose: {meta.get('previousClose', meta.get('chartPreviousClose'))}")
        print(f"  marketState: {meta.get('marketState')}")
        ts = meta.get("regularMarketTime", 0)
        if ts:
            from datetime import datetime
            t = datetime.fromtimestamp(ts)
            print(f"  last update: {t}")
except Exception as e:
    print(f"  Error: {e}")

# 6. CMoney / MoneyDJ
print("\n--- MoneyDJ ---")
test_api("MoneyDJ quote", "https://www.moneydj.com/kmdj/wiki/wikiviewer.aspx", {"keyroot": "a9801234"})

# 7. TWSE open data (data.gov.tw)
print("\n--- data.gov.tw ---")
test_api("gov open data", "https://opendata.epa.gov.tw/webapi/api/rest/datastore",
         {"action": "JSON", "callback": "", "resource_id": "355"})
