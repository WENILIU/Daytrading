"""
Gap Fade v3 - TWSE Full Market Scanner (OPTIMIZED)
Full market scan in ~5 seconds. Free, no auth, no subscription limit.
"""
import requests, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from dataclasses import dataclass
from typing import List, Optional

TWSE_API = "http://mis.twse.com.tw/stock/api/getStockInfo.jsp"
BATCH_SIZE = 100
MAX_WORKERS = 15

# Connection pool (keep-alive)
_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0"})
_adapter = HTTPAdapter(pool_connections=25, pool_maxsize=25)
_session.mount("http://", _adapter)


@dataclass
class GapSignal:
    code: str
    market: int
    open_price: float
    prev_close: float
    gap_pct: float
    current_price: float
    volume: int


def _query_batch(codes: List[str], market: int = 0) -> List[dict]:
    prefix = "tse" if market == 0 else "otc"
    parts = [f"{prefix}_{c}.tw" for c in codes]
    ex_ch = "|".join(parts)
    url = f"{TWSE_API}?ex_ch={ex_ch}&_={int(time.time()*1000)}"
    try:
        r = _session.get(url, timeout=8)
        if r.status_code != 200:
            return []
        text = r.text.strip()
        idx = text.find("{")
        if idx < 0:
            return []
        return json.loads(text[idx:]).get("msgArray", [])
    except:
        return []


def scan_market(stock_list: List[str], gap_threshold: float = 0.05) -> List[GapSignal]:
    """
    Scan all stocks for gaps. ~5 seconds for full market.
    Returns GapSignals sorted by |gap| descending.
    """
    t0 = time.time()
    batches = [stock_list[i:i+BATCH_SIZE] for i in range(0, len(stock_list), BATCH_SIZE)]

    all_raw = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(_query_batch, b) for b in batches]
        for f in as_completed(futures):
            all_raw.extend(f.result())

    signals = []
    for s in all_raw:
        try:
            o_str = s.get("o", "-")
            y_str = s.get("y", "-")
            if o_str == "-" or y_str == "-":
                continue
            o = float(o_str)
            y = float(y_str)
            if o <= 0 or y <= 0:
                continue
            gap = (o - y) / y
            if abs(gap) >= gap_threshold:
                z_str = s.get("z", "-")
                z = float(z_str) if z_str != "-" else 0
                v_str = s.get("v", "0")
                v = int(v_str) if v_str and v_str.replace("-","").isdigit() else 0
                ex = s.get("ex", "tse")
                signals.append(GapSignal(
                    code=s.get("c", ""),
                    market=0 if ex == "tse" else 1,
                    open_price=o,
                    prev_close=y,
                    gap_pct=round(gap * 100, 2),
                    current_price=z,
                    volume=v,
                ))
        except:
            continue

    signals.sort(key=lambda x: abs(x.gap_pct), reverse=True)
    elapsed = time.time() - t0
    print(f"[SCAN] {len(stock_list)} codes -> {len(all_raw)} data -> {len(signals)} gaps | {elapsed:.1f}s")
    return signals


if __name__ == "__main__":
    print("=" * 60)
    print("  GAP FADE v3 - TWSE FULL MARKET SCANNER")
    print("  Full market in ~5s | Free | No auth required")
    print("=" * 60)

    # Load stock list
    try:
        with open("valid_stocks.txt") as f:
            stocks = [s.strip() for s in f if s.strip()]
    except:
        with open("all_stocks.txt") as f:
            stocks = [s.strip() for s in f if s.strip()]

    print(f"\n  Stocks: {len(stocks)}")
    print(f"  Threshold: |gap| >= 5%")
    print(f"  Workers: {MAX_WORKERS}, Batch: {BATCH_SIZE}")

    signals = scan_market(stocks, gap_threshold=0.05)

    if signals:
        print(f"\n  {'Code':<6} {'Gap%':>7} {'Open':>8} {'Prev':>8} {'Now':>8} {'Vol':>10}")
        print("  " + "-" * 55)
        for s in signals:
            print(f"  {s.code:<6} {s.gap_pct:>+6.1f}% {s.open_price:>8.2f} {s.prev_close:>8.2f} {s.current_price:>8.2f} {s.volume:>10}")
    else:
        print("\n  No gaps found.")
