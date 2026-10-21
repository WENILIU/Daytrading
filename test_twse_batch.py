import requests, json, time

# TWSE intraday API - supports multiple stocks in one request!
# Format: ex_ch=tse_2330.tw|tse_2454.tw|otc_XXXX.tw

def test_twse_batch(stocks, market_map=None):
    """Query TWSE intraday API for multiple stocks."""
    # Build ex_ch parameter
    parts = []
    for s in stocks:
        if market_map and s in market_map:
            prefix = "tse" if market_map[s] == 0 else "otc"
        else:
            prefix = "tse"  # default to listed
        parts.append(f"{prefix}_{s}.tw")
    
    ex_ch = "|".join(parts)
    url = f"http://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&_={int(time.time()*1000)}"
    
    headers = {"User-Agent": "Mozilla/5.0"}
    t0 = time.time()
    r = requests.get(url, headers=headers, timeout=15)
    elapsed = time.time() - t0
    
    print(f"  Status: {r.status_code} Time: {elapsed:.2f}s Size: {len(r.text)}")
    if r.status_code == 200:
        data = r.json()
        stock_list = data.get("data", {}).get("stock", []) if isinstance(data.get("data"), dict) else data.get("stock", [])
        print(f"  Stocks returned: {len(stock_list)}")
        if stock_list:
            s = stock_list[0]
            print(f"  Sample: id={s.get('id')} name={s.get('name')}")
            print(f"    open={s.get('o')} high={s.get('h')} low={s.get('l')} close={s.get('z')}")
            print(f"    prev_close={s.get('pc')} vol={s.get('tv')}")
        return stock_list
    return []

# Test 1: Single stock
print("=== Single Stock ===")
test_twse_batch(["2330"])

# Test 2: 10 stocks
print("\n=== 10 Stocks ===")
test_twse_batch(["2330", "2454", "2317", "2303", "6505", "2324", "2383", "3711", "2412", "2357"])

# Test 3: 50 stocks
print("\n=== 50 Stocks ===")
stocks_50 = [str(2300+i) for i in range(50)]
test_twse_batch(stocks_50)

# Test 4: 100 stocks
print("\n=== 100 Stocks ===")
stocks_100 = [str(2300+i) for i in range(100)]
test_twse_batch(stocks_100)

# Test 5: 200 stocks
print("\n=== 200 Stocks ===")
stocks_200 = [str(2300+i) for i in range(200)]
test_twse_batch(stocks_200)
