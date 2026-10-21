import requests, json

# TWSE 處置股
url = "https://www.twse.com.tw/zh/api/tradingReference/stockRestriction"
resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
resp.encoding = 'utf-8'
print(f"TWSE status: {resp.status_code}")
try:
    data = resp.json()
    print(f"Keys: {list(data.keys())}")
    print(f"Total rows: {data.get('total', 'N/A')}")
    rows = data.get('data', [])
    print(f"Data rows: {len(rows)}")
    if rows:
        print(f"First 5:")
        for r in rows[:5]:
            print(f"  {r}")
except Exception as e:
    print(f"Parse error: {e}")
    print(f"Raw: {resp.text[:300]}")

# TPEx
print("\n--- TPEx ---")
url2 = "https://www.tpex.org.tw/web/stock/aftertrading/stocksuspension/stk_suspension.php?l=zh-tw&o=json"
resp2 = requests.get(url2, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
resp2.encoding = 'utf-8'
print(f"TPEx status: {resp2.status_code}")
try:
    data2 = resp2.json()
    print(f"Keys: {list(data2.keys())}")
    rows2 = data2.get('data', [])
    print(f"Data rows: {len(rows2)}")
    if rows2:
        for r in rows2[:3]:
            print(f"  {r}")
except Exception as e:
    print(f"Parse error: {e}")
