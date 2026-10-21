"""
Extract 1-min volume features for Gap Fade signals.
Strategy: For each stock, read year-month files (which cover full years).
Fall back to daily files only if year-month file doesn't cover the date.
Outputs: features CSV for analysis.
"""
import pandas as pd, numpy as np, json, time, sqlite3
from pathlib import Path
from collections import defaultdict
import os

# Load index
with open(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_path_index.json", "r", encoding="utf-8") as f:
    INDEX = json.load(f)

# Load signals
df = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")
df["date"] = pd.to_datetime(df["date"])

# Simulate PnL
def simulate_pnl(row, sl=0.06, tp=0.04, cost=0.0017):
    entry=row["entry"]; d=row["direction"]; hi=row["day_high"]; lo=row["day_low"]; cl=row["day_close"]
    if d=="SHORT":
        sl_p=entry*(1+sl); tp_p=entry*(1-tp)
        ep = sl_p if hi>=sl_p else (tp_p if lo<=tp_p else cl)
        return (entry-ep)/entry - 2*cost
    else:
        sl_p=entry*(1-sl); tp_p=entry*(1+tp)
        ep = sl_p if lo<=sl_p else (tp_p if hi>=tp_p else cl)
        return (ep-entry)/entry - 2*cost

df["pnl"] = df.apply(simulate_pnl, axis=1)
df["win"] = (df["pnl"] > 0).astype(int)

# Market condition
df["mkt_cond"] = "flat"
df.loc[df["market_ret"] > 0.02, "mkt_cond"] = "up2"
df.loc[df["market_ret"] < -0.02, "mkt_cond"] = "down2"

# Focus on signals 2023+ (where we have 1-min data)
target = df[(df["date"].dt.year >= 2023)].copy()
print(f"Target signals (2023+): {len(target)}")
print(f"  SHORT: {len(target[target['direction']=='SHORT'])}")
print(f"  LONG:  {len(target[target['direction']=='LONG'])}")

# Group by stock for efficient file access
stock_groups = defaultdict(list)  # stock -> [signal indices]
for idx, row in target.iterrows():
    stock_groups[row["stock"]].append(idx)

print(f"\nUnique stocks to process: {len(stock_groups)}")

# Process files
def extract_features_for_date(today_bars, prev_bars):
    """Extract volume features for one day given its bars and previous day's bars."""
    vol_today = sum(b.get("volume", 0) for b in today_bars)
    vol_prev = sum(b.get("volume", 0) for b in prev_bars)
    if vol_prev == 0 or vol_today == 0:
        return None

    first5 = [b for b in today_bars if b.get("date", "")[11:16] < "09:05"]
    vol_first5 = sum(b.get("volume", 0) for b in first5)

    first15 = [b for b in today_bars if b.get("date", "")[11:16] < "09:15"]
    vol_first15 = sum(b.get("volume", 0) for b in first15)

    open_price = today_bars[0].get("open", 0) if today_bars else 0
    price_905 = first5[-1].get("close", 0) if first5 else 0
    price_915 = first15[-1].get("close", 0) if first15 else 0

    price_chg_5 = (price_905 - open_price) / open_price if open_price > 0 else 0
    price_chg_15 = (price_915 - open_price) / open_price if open_price > 0 else 0

    vol_conc_5 = vol_first5 / vol_today if vol_today > 0 else 0
    vol_conc_15 = vol_first15 / vol_today if vol_today > 0 else 0
    vol_ratio = vol_today / vol_prev
    dollar_vol = sum(b.get("volume", 0) * b.get("close", 0) for b in today_bars)

    return {
        "vol_today": vol_today, "vol_prev": vol_prev, "vol_ratio": vol_ratio,
        "vol_first5": vol_first5, "vol_first15": vol_first15,
        "vol_conc_5": vol_conc_5, "vol_conc_15": vol_conc_15,
        "price_chg_5min": price_chg_5, "price_chg_15min": price_chg_15,
        "dollar_vol": dollar_vol,
    }


def load_all_bars_for_stock(stock, folder):
    """Load all 1-min bars for a stock from available files. Returns dict: date_str -> [bars]."""
    all_by_date = defaultdict(list)

    # Read year-month files first (they cover full years)
    for fname in sorted(os.listdir(folder)):
        if not fname.endswith('.json'):
            continue
        # Skip daily files (YYYY-MM-DD format) - we'll use them only as fallback
        parts = fname.replace('.json', '').split('_')
        if len(parts) == 2 and len(parts[1]) == 10:
            continue
        fpath = os.path.join(folder, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            if not isinstance(raw, dict) or 'data' not in raw:
                continue
            for b in raw['data']:
                d = b.get('date', '')[:10]
                if d:
                    all_by_date[d].append(b)
        except:
            continue

    return all_by_date


# Process all stocks
t0 = time.time()
all_features = []
processed_stocks = 0
errors = 0

for stock, indices in stock_groups.items():
    folder = INDEX.get(stock)
    if not folder or not os.path.isdir(folder):
        errors += 1
        continue

    # Load all bars for this stock
    all_by_date = load_all_bars_for_stock(stock, folder)
    if not all_by_date:
        errors += 1
        continue

    sorted_dates = sorted(all_by_date.keys())

    # For each signal, extract features
    for idx in indices:
        row = target.loc[idx]
        date_str = row["date"].strftime("%Y-%m-%d")

        if date_str not in all_by_date:
            continue

        today_bars = sorted(all_by_date[date_str], key=lambda x: x.get("date", ""))

        # Find previous trading day
        prev_dates = [d for d in sorted_dates if d < date_str]
        if not prev_dates:
            continue
        prev_bars = sorted(all_by_date[prev_dates[-1]], key=lambda x: x.get("date", ""))

        feat = extract_features_for_date(today_bars, prev_bars)
        if feat is None:
            continue

        all_features.append({
            "date": row["date"], "stock": stock, "direction": row["direction"],
            "mkt_cond": row["mkt_cond"], "adj_gap": row["adj_gap"],
            "pnl": row["pnl"], "win": row["win"],
            **feat
        })

    processed_stocks += 1
    if processed_stocks % 100 == 0:
        elapsed = time.time() - t0
        print(f"  Progress: {processed_stocks}/{len(stock_groups)} stocks, {len(all_features)} features, {elapsed:.0f}s")

elapsed = time.time() - t0
print(f"\nDone: {processed_stocks} stocks, {len(all_features)} features, {errors} errors, {elapsed:.0f}s")

# Save to CSV
out_path = r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\volume_features.csv"
if all_features:
    feat_df = pd.DataFrame(all_features)
    feat_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"Saved: {out_path}")
    print(f"Shape: {feat_df.shape}")
