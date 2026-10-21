"""
Gap Fade v3 - Full Day Simulation
Replays 2025-04-14 using 1-min data to show complete trading flow.
"""
import json, pickle, time, sys, io
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ============================================================
# CONFIG (same as live)
# ============================================================
CAPITAL = 4_500_000
GAP_THRESHOLD = 0.03
MIN_PRICE = 30
MAX_PRICE = 225
CONFIRM_MINUTES = 15
STOP_LOSS_PCT = 0.06
TAKE_PROFIT_PCT = 0.04
FORCE_EXIT = "13:25"
BASE_POS_PCT = 0.05
LONG_POS_PCT = 0.025
COST_PER_TRADE = 0.0023
MAX_POSITIONS = 8

TIERS = [
    (0.03, 999, 2.0, "T5"),
    (0.015, 0.03, 1.5, "T4"),
    (0.005, 0.015, 1.0, "T3"),
    (0.0, 0.005, 0.5, "T2"),
]

# ============================================================
# LOAD DATA
# ============================================================
TARGET_DATE = "2025-04-14"
INDEX_PATH = Path(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_1min_index.pkl")

with open(INDEX_PATH, "rb") as f:
    stock_index = pickle.load(f)

print(f"=" * 70)
print(f"  GAP FADE v3 - FULL DAY SIMULATION")
print(f"  Date: {TARGET_DATE}")
print(f"  Capital: {CAPITAL:,}")
print(f"=" * 70)

# Load 1-min data for target date
def load_1min(stock_code, date_str):
    """Load 1-min bars for a specific date"""
    folder = stock_index.get(stock_code)
    if not folder:
        return None
    folder = Path(folder)
    # Try monthly file
    month_file = folder / f"{stock_code}_{date_str[:7]}.json"
    if month_file.exists():
        with open(month_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        bars = [b for b in data.get("data", []) if b.get("date", "").startswith(date_str)]
        return bars if bars else None
    # Try daily file
    daily_file = folder / f"{stock_code}_{date_str}.json"
    if daily_file.exists():
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("data", [])
    return None

def load_prev_close(stock_code, date_str):
    """Get previous day close from 1-min data"""
    folder = stock_index.get(stock_code)
    if not folder:
        return 0
    folder = Path(folder)
    # Parse date to get previous trading day
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    # Try previous days (skip weekends)
    for offset in range(1, 8):
        prev_dt = dt.replace(day=dt.day - offset) if dt.day > offset else None
        if prev_dt is None:
            continue
        prev_str = prev_dt.strftime("%Y-%m-%d")
        bars = load_1min(stock_code, prev_str)
        if bars:
            return bars[-1].get("close", 0)
    return 0

# ============================================================
# STEP 1: 9:00 SCAN
# ============================================================
print(f"\n{'='*70}")
print(f"  STEP 1: 9:00 AM - SCANNING FOR GAP SIGNALS")
print(f"{'='*70}")

# First, get market gap from TAIEX (use 0000 or estimate from large caps)
# For simulation, we calculate from the data
market_gaps = []
basket = ["2330", "2317", "2454", "2303", "6505", "3711", "2412"]
for sym in basket:
    bars = load_1min(sym, TARGET_DATE)
    if bars:
        open_price = bars[0].get("open", 0)
        prev = load_prev_close(sym, TARGET_DATE)
        if prev > 0 and open_price > 0:
            market_gaps.append((open_price - prev) / prev)

market_gap = np.mean(market_gaps) if market_gaps else 0
print(f"\n  Market gap (TAIEX proxy): {market_gap*100:+.2f}%")

# Scan all stocks
t0 = time.time()
signals = []
scanned = 0

for stock_code in stock_index.keys():
    bars = load_1min(stock_code, TARGET_DATE)
    if not bars or len(bars) < 2:
        continue
    scanned += 1

    open_price = bars[0].get("open", 0)
    prev_close = load_prev_close(stock_code, TARGET_DATE)

    if prev_close < MIN_PRICE or prev_close > MAX_PRICE:
        continue
    if open_price <= 0:
        continue

    raw_gap = (open_price - prev_close) / prev_close
    adj_gap = raw_gap - market_gap

    direction = None
    if adj_gap > GAP_THRESHOLD:
        direction = "SHORT"
    elif adj_gap < -GAP_THRESHOLD:
        direction = "LONG"

    if direction:
        signals.append({
            "stock": stock_code,
            "direction": direction,
            "open_price": open_price,
            "prev_close": prev_close,
            "raw_gap": raw_gap,
            "adj_gap": adj_gap,
            "bars": bars,
        })

scan_time = time.time() - t0
signals.sort(key=lambda s: abs(s["adj_gap"]), reverse=True)
signals = signals[:MAX_POSITIONS]

print(f"  Scanned: {scanned} stocks in {scan_time:.1f}s")
print(f"  Found: {len(signals)} signals (top {MAX_POSITIONS} by |gap|)")
print(f"\n  {'Stock':<8} {'Dir':<6} {'Open':>8} {'PrevClose':>10} {'RawGap':>8} {'AdjGap':>8}")
print(f"  {'-'*8} {'-'*6} {'-'*8} {'-'*10} {'-'*8} {'-'*8}")
for s in signals:
    print(f"  {s['stock']:<8} {s['direction']:<6} {s['open_price']:>8.1f} {s['prev_close']:>10.1f} {s['raw_gap']*100:>+7.2f}% {s['adj_gap']*100:>+7.2f}%")

# ============================================================
# STEP 2: 9:15 CONFIRMATION
# ============================================================
print(f"\n{'='*70}")
print(f"  STEP 2: 9:15 AM - CONFIRMATION CHECK")
print(f"{'='*70}")
print(f"  Rule: Price must move in our direction for >= {CONFIRM_MINUTES} min")
print(f"  SHORT: price must DROP from open (drop > 0%)")
print(f"  LONG:  price must RISE from open (rise > 0%)")

confirmed = []
for s in signals:
    # Get price at 9:15 (bar index 14, since 9:01 is index 0)
    target_time = "09:15"
    price_915 = None
    for bar in s["bars"]:
        bar_time = bar.get("date", "")[11:16]
        if bar_time == target_time:
            price_915 = bar.get("close", 0)
            break
    # Fallback: use bar at index 14
    if price_915 is None and len(s["bars"]) > 14:
        price_915 = s["bars"][14].get("close", 0)

    if price_915 is None or price_915 <= 0:
        print(f"\n  {s['stock']} {s['direction']}: NO DATA at 9:15, SKIP")
        continue

    # Calculate 15-min move
    if s["direction"] == "SHORT":
        move = (s["open_price"] - price_915) / s["open_price"]
    else:
        move = (price_915 - s["open_price"]) / s["open_price"]

    # Determine tier
    tier = None
    multiplier = 0
    for min_drop, max_drop, mult, label in TIERS:
        if min_drop <= move < max_drop:
            tier = label
            multiplier = mult
            break

    if move <= 0:
        print(f"\n  {s['stock']} {s['direction']}: move={move*100:+.2f}% -> NOT CONFIRMED, SKIP")
        continue

    # Calculate position
    if s["direction"] == "SHORT":
        base_value = CAPITAL * BASE_POS_PCT
    else:
        base_value = CAPITAL * LONG_POS_PCT
    position_value = base_value * multiplier
    shares = int(position_value / price_915 / 1000) * 1000

    if shares < 1000:
        print(f"\n  {s['stock']} {s['direction']}: move={move*100:+.2f}% [{tier}] -> < 1 zhang, SKIP")
        continue

    # SL/TP prices
    if s["direction"] == "SHORT":
        sl_price = round(price_915 * (1 + STOP_LOSS_PCT), 1)
        tp_price = round(price_915 * (1 - TAKE_PROFIT_PCT), 1)
    else:
        sl_price = round(price_915 * (1 - STOP_LOSS_PCT), 1)
        tp_price = round(price_915 * (1 + TAKE_PROFIT_PCT), 1)

    confirmed.append({
        **s,
        "entry_price": price_915,
        "entry_time": "09:15",
        "move_15min": move,
        "tier": tier,
        "multiplier": multiplier,
        "shares": shares,
        "sl_price": sl_price,
        "tp_price": tp_price,
    })

    print(f"\n  {s['stock']} {s['direction']}: move={move*100:+.2f}% -> CONFIRMED [{tier}]")
    print(f"    Entry: {price_915:.1f} x {shares:,} shares")
    print(f"    SL: {sl_price:.1f} ({STOP_LOSS_PCT*100:.0f}%) | TP: {tp_price:.1f} ({TAKE_PROFIT_PCT*100:.0f}%)")
    print(f"    Force close: {FORCE_EXIT}")

# ============================================================
# STEP 3: ORDER PLACEMENT (Smart Trade)
# ============================================================
print(f"\n{'='*70}")
print(f"  STEP 3: ORDER PLACEMENT (SKCOM Smart Trade)")
print(f"{'='*70}")
print(f"  Using SendStockStrategyDayTrade with built-in SL/TP/ForceClose")

total_exposure = 0
orders = []
for pos in confirmed:
    actual_value = pos["shares"] * pos["entry_price"]
    if total_exposure + actual_value > CAPITAL:
        print(f"\n  {pos['stock']}: EXPOSURE LIMIT, SKIP")
        continue
    total_exposure += actual_value

    if pos["direction"] == "SHORT":
        order_desc = f"融券賣出 (SHORT)"
        sl_desc = f"融券買回 @ {pos['sl_price']:.1f} (停損觸發: 價格漲到 {pos['sl_price']:.1f})"
        tp_desc = f"融券買回 @ {pos['tp_price']:.1f} (停利觸發: 價格跌到 {pos['tp_price']:.1f})"
    else:
        order_desc = f"現股買進 (LONG)"
        sl_desc = f"現股賣出 @ {pos['sl_price']:.1f} (停損觸發: 價格跌到 {pos['sl_price']:.1f})"
        tp_desc = f"現股賣出 @ {pos['tp_price']:.1f} (停利觸發: 價格漲到 {pos['tp_price']:.1f})"

    print(f"\n  ORDER: {pos['stock']} {order_desc}")
    print(f"    進場: {pos['entry_price']:.1f} x {pos['shares']:,} = {actual_value:,.0f}")
    print(f"    預掛停損: {sl_desc}")
    print(f"    預掛停利: {tp_desc}")
    print(f"    強制平倉: {FORCE_EXIT}")

    # SKCOM Smart Trade parameters
    sl_pct = f"{STOP_LOSS_PCT*100:.0f}"
    tp_pct = f"{TAKE_PROFIT_PCT*100:.0f}"
    print(f"    [SKCOM] STOCKSTRATEGYORDER:")
    print(f"      bstrStockNo = \"{pos['stock']}\"")
    print(f"      nBuySell = {0 if pos['direction']=='LONG' else 1}")
    print(f"      bstrOrderPrice = \"{pos['entry_price']}\"")
    print(f"      nQty = {pos['shares']}")
    print(f"      nStopLossFlag = 1, bstrSLPerent = \"{sl_pct}\"")
    print(f"      nTakeProfitFlag = 1, bstrTPPercnet = \"{tp_pct}\"")
    print(f"      nClearAllFlag = 1, bstrClearCancelTime = \"1325\"")

    orders.append(pos)

print(f"\n  Total exposure: {total_exposure:,.0f} ({total_exposure/CAPITAL*100:.0f}%)")

# ============================================================
# STEP 4: REPLAY (minute-by-minute SL/TP check)
# ============================================================
print(f"\n{'='*70}")
print(f"  STEP 4: INTRADAY REPLAY (checking SL/TP triggers)")
print(f"{'='*70}")

results = []
for pos in orders:
    print(f"\n  --- {pos['stock']} {pos['direction']} ---")
    print(f"  Entry: {pos['entry_price']:.1f} | SL: {pos['sl_price']:.1f} | TP: {pos['tp_price']:.1f}")

    exit_price = None
    exit_reason = None
    exit_time = None

    # Replay from 9:16 onwards
    for bar in pos["bars"]:
        bar_time = bar.get("date", "")[11:16]
        if bar_time < "09:16":
            continue
        if bar_time >= FORCE_EXIT.replace(":", ""):
            break

        high = bar.get("high", 0)
        low = bar.get("low", 0)

        if pos["direction"] == "SHORT":
            # SL: price goes UP to sl_price
            if high >= pos["sl_price"]:
                exit_price = pos["sl_price"]
                exit_reason = "STOP_LOSS"
                exit_time = bar_time
                break
            # TP: price goes DOWN to tp_price
            if low <= pos["tp_price"]:
                exit_price = pos["tp_price"]
                exit_reason = "TAKE_PROFIT"
                exit_time = bar_time
                break
        else:
            # SL: price goes DOWN to sl_price
            if low <= pos["sl_price"]:
                exit_price = pos["sl_price"]
                exit_reason = "STOP_LOSS"
                exit_time = bar_time
                break
            # TP: price goes UP to tp_price
            if high >= pos["tp_price"]:
                exit_price = pos["tp_price"]
                exit_reason = "TAKE_PROFIT"
                exit_time = bar_time
                break

    # Force close if still open
    if exit_price is None:
        # Get price at force close time
        for bar in reversed(pos["bars"]):
            bar_time = bar.get("date", "")[11:16]
            if bar_time <= "13:25":
                exit_price = bar.get("close", pos["entry_price"])
                exit_reason = "FORCE_CLOSE"
                exit_time = "13:25"
                break
        if exit_price is None:
            exit_price = pos["bars"][-1].get("close", pos["entry_price"])
            exit_reason = "FORCE_CLOSE"
            exit_time = "13:30"

    # Calculate PnL
    if pos["direction"] == "SHORT":
        pnl = (pos["entry_price"] - exit_price) * pos["shares"]
    else:
        pnl = (exit_price - pos["entry_price"]) * pos["shares"]
    cost = (pos["entry_price"] + exit_price) * pos["shares"] * COST_PER_TRADE
    pnl -= cost

    print(f"  EXIT: {exit_price:.1f} @ {exit_time} [{exit_reason}]")
    print(f"  PnL: {pnl:+,.0f} (cost: {cost:,.0f})")

    results.append({
        "stock": pos["stock"], "direction": pos["direction"],
        "tier": pos["tier"], "entry": pos["entry_price"],
        "exit": exit_price, "exit_time": exit_time,
        "reason": exit_reason, "shares": pos["shares"],
        "pnl": pnl, "cost": cost,
    })

# ============================================================
# FINAL REPORT
# ============================================================
print(f"\n{'='*70}")
print(f"  DAILY REPORT - {TARGET_DATE}")
print(f"{'='*70}")

df = pd.DataFrame(results)
total_pnl = df["pnl"].sum()
wins = (df["pnl"] > 0).sum()
total = len(df)

print(f"\n  Trades: {total}")
print(f"  Win rate: {wins}/{total} ({wins/total*100:.1f}%)")
print(f"  Total PnL: {total_pnl:+,.0f}")
print(f"  Total cost: {df['cost'].sum():,.0f}")
print(f"  Return: {total_pnl/CAPITAL*100:+.2f}%")

print(f"\n  {'Stock':<8} {'Dir':<6} {'Tier':<4} {'Entry':>8} {'Exit':>8} {'Time':>6} {'Reason':<12} {'PnL':>10}")
print(f"  {'-'*8} {'-'*6} {'-'*4} {'-'*8} {'-'*8} {'-'*6} {'-'*12} {'-'*10}")
for r in results:
    print(f"  {r['stock']:<8} {r['direction']:<6} {r['tier']:<4} {r['entry']:>8.1f} {r['exit']:>8.1f} {r['exit_time']:>6} {r['reason']:<12} {r['pnl']:>+10,.0f}")

# Cleanup
import os
for f in ["_find_date.py"]:
    fp = Path(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs") / f
    if fp.exists():
        os.remove(fp)
