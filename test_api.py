import requests
import json

# Try different TWSE endpoints for 處置股
endpoints = [
    # Method 1: stockRestriction
    ("TWSE restriction", "https://www.twse.com.tw/zh/api/tradingReference/stockRestriction"),
    # Method 2: 處置股公告
    ("TWSE chuzhi", "https://www.twse.com.tw/zh/api/tradingReference/INTEREL005"),
    # Method 3: 當日處置股
    ("TWSE daily", "https://www.twse.com.tw/data/tradingReference/INTEREL005.json?date=20261017&output=json"),
    # Method 4: TPEx
    ("TPEx restriction", "https://www.tpex.org.tw/web/stock/notice/stock_restriction.php?l=zh-tw"),
]

for name, url in endpoints:
    try:
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        print(f"\n{name}: status={resp.status_code}")
        if resp.status_code == 200:
            text = resp.text[:500]
            print(f"  Response: {text}")
    except Exception as e:
        print(f"\n{name}: ERROR - {e}")
