import requests, json, time

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.twse.com.tw/zh/page/trading/final/STOCK.html",
    "Accept": "application/json",
}

# TWSE "當日股票成交" - all stocks daily data
print("=== TWSE All Stocks Daily ===")
urls = [
    ("MLDAY (all stocks)", "https://www.twse.com.tw/exchangeReport/MLDAY", {"response": "json", "date": "20261020"}),
    ("STOCK_DAY 2330", "https://www.twse.com.tw/exchangeReport/STOCK_DAY", {"response": "json", "date": "20261020", "stockId": "2330"}),
    ("TIINDDAY (intraday)", "https://www.twse.com.tw/exchangeReport/TIINDDAY", {"response": "json"}),
    ("MLDAY no date", "https://www.twse.com.tw/exchangeReport/MLDAY", {"response": "json"}),
]

for name, url, params in urls:
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        is_json = r.status_code == 200 and r.text.strip()[:1] in "[{"
        print(f"\n{name}: {r.status_code} json={is_json}")
        if is_json:
            data = r.json()
            if isinstance(data, dict):
                print(f"  stat={data.get('stat')} total={data.get('total')}")
                fields = data.get("fields", [])
                rows = data.get("data", [])
                print(f"  fields({len(fields)}): {fields[:10]}")
                if rows:
                    print(f"  rows: {len(rows)}")
                    print(f"  row0: {rows[0][:8]}")
                    if len(rows) > 1:
                        print(f"  row1: {rows[1][:8]}")
            elif isinstance(data, list):
                print(f"  list: {len(data)} items")
                if data:
                    print(f"  item0: {str(data[0])[:200]}")
    except Exception as e:
        print(f"{name}: {str(e)[:80]}")

# Also try the TWSE "盤中個股行情" intraday endpoint
print("\n\n=== TWSE Intraday ===")
intraday_urls = [
    ("intraday stock", "https://www.twse.com.tw/intraday/api/stockPrice", {}),
    ("intraday all", "https://www.twse.com.tw/intraday/api/allStockPrice", {}),
    ("intraday v1", "https://www.twse.com.tw/v1/intraday/stockPrice", {}),
]
for name, url, params in intraday_urls:
    try:
        r = requests.get(url, headers=headers, params=params, timeout=8)
        is_json = r.status_code == 200 and r.text.strip()[:1] in "[{"
        print(f"{name}: {r.status_code} json={is_json} len={len(r.text)}")
        if is_json:
            data = r.json()
            if isinstance(data, list):
                print(f"  {len(data)} items, sample: {str(data[0])[:150]}")
    except Exception as e:
        print(f"{name}: {str(e)[:60]}")
