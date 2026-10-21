import requests, json, time

def query_twse_batch(codes, market=0):
    """Query TWSE intraday API. market: 0=tse, 1=otc"""
    prefix = "tse" if market == 0 else "otc"
    parts = [f"{prefix}_{c}.tw" for c in codes]
    ex_ch = "|".join(parts)
    url = f"http://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&_={int(time.time()*1000)}"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    if r.status_code != 200:
        return []
    # Response has leading whitespace/newlines before JSON
    text = r.text.strip()
    if not text.startswith("{"):
        # Find the JSON start
        idx = text.find("{")
        if idx < 0:
            return []
        text = text[idx:]
    data = json.loads(text)
    return data.get("msgArray", [])

# Load valid stock codes
with open("all_stocks.txt") as f:
    all_stocks = [s.strip() for s in f if s.strip()]

# Test batch sizes with VALID codes
print("=== Batch Size Test (valid codes) ===")
for batch_size in [10, 20, 50, 100, 200]:
    batch = all_stocks[:batch_size]
    t0 = time.time()
    try:
        results = query_twse_batch(batch)
        elapsed = time.time() - t0
        valid = [r for r in results if r.get("o") and r.get("y") and r["o"] != "-" and r["y"] != "-"]
        print(f"  {batch_size:3d} codes: {len(results)} returned, {len(valid)} valid, {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  {batch_size:3d} codes: ERROR {str(e)[:60]} ({elapsed:.1f}s)")
    time.sleep(0.5)

# Test full scan: all stocks in batches of 50
print("\n=== Full Scan (all stocks, batch=50) ===")
t0 = time.time()
all_results = []
for i in range(0, len(all_stocks), 50):
    batch = all_stocks[i:i+50]
    try:
        results = query_twse_batch(batch)
        all_results.extend(results)
    except Exception as e:
        pass  # skip failed batches
    if i % 200 == 0:
        elapsed = time.time() - t0
        print(f"  Progress: {i+len(batch)}/{len(all_stocks)} ({elapsed:.1f}s)")

total_time = time.time() - t0
print(f"\n  Total: {len(all_results)} stocks in {total_time:.1f}s")

# Calculate gaps
gaps = []
for s in all_results:
    try:
        o = float(s.get("o", "0").replace("-", "0"))
        y = float(s.get("y", "0").replace("-", "0"))
        if o > 0 and y > 0:
            gap = (o - y) / y
            if abs(gap) >= 0.05:
                gaps.append({
                    "code": s.get("c", ""),
                    "open": o, "prev_close": y,
                    "gap_pct": round(gap * 100, 2),
                    "close": float(s.get("z", "0").replace("-", "0") or 0),
                    "volume": int(s.get("v", "0") or 0),
                })
    except:
        continue

print(f"  |gap|>=5%: {len(gaps)}")
if gaps:
    gaps.sort(key=lambda x: abs(x["gap_pct"]), reverse=True)
    print(f"\n  {'Code':<6} {'Gap%':>7} {'Open':>8} {'Prev':>8}")
    for g in gaps[:20]:
        print(f"  {g['code']:<6} {g['gap_pct']:>+6.1f}% {g['open']:>8.2f} {g['prev_close']:>8.2f}")
