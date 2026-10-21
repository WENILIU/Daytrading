"""
Full volume analysis for Gap Fade signals (2023-2026).
Goal: find features that improve win rate from 60% to 80%+.
"""
import pandas as pd, numpy as np, json, time
from pathlib import Path
from collections import defaultdict

with open(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_path_index.json", "r", encoding="utf-8") as f:
    INDEX = json.load(f)

df = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")
df["date"] = pd.to_datetime(df["date"])

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

# Filter to 2023+ (where we have 1-min data)
df_recent = df[df["date"] >= "2023-01-01"].copy()
print(f"Signals 2023+: {len(df_recent)}")

# Market condition groups
def mkt_group(mr):
    if mr > 0.02: return "MKT_UP"
    elif mr < -0.02: return "MKT_DOWN"
    else: return "MKT_FLAT"

df_recent["mkt_group"] = df_recent["market_ret"].apply(mkt_group)
print(f"  MKT_FLAT: {len(df_recent[df_recent['mkt_group']=='MKT_FLAT'])}")
print(f"  MKT_UP: {len(df_recent[df_recent['mkt_group']=='MKT_UP'])}")
print(f"  MKT_DOWN: {len(df_recent[df_recent['mkt_group']=='MKT_DOWN'])}")

# Cache loaded files to avoid re-reading
_file_cache = {}

def load_1min_features(stock, date):
    """Load 1-min data and extract features for target date."""
    folder = INDEX.get(stock)
    if not folder: return None
    
    # Try monthly files (filename = start month, but contains more)
    # Try the target month and previous months
    ym = date.strftime("%Y-%m")
    # Try current month file, and a few previous
    candidates = [ym]
    for offset in range(1, 13):
        prev = (date.replace(day=1) - pd.DateOffset(months=offset)).strftime("%Y-%m")
        candidates.append(prev)
    
    bars = None
    for try_ym in candidates:
        cache_key = f"{stock}_{try_ym}"
        if cache_key in _file_cache:
            bars = _file_cache[cache_key]
            if bars is not None:
                break
            continue
        
        fpath = Path(folder) / f"{stock}_{try_ym}.json"
        if not fpath.exists():
            _file_cache[cache_key] = None
            continue
        
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict) and "data" in raw:
                bars = raw["data"]
                _file_cache[cache_key] = bars
                break
            else:
                _file_cache[cache_key] = None
        except:
            _file_cache[cache_key] = None
    
    if not bars: return None
    
    # Extract target date bars
    date_str = date.strftime("%Y-%m-%d")
    today_bars = [b for b in bars if b.get("date","").startswith(date_str)]
    if not today_bars: return None
    
    # Previous day bars
    all_dates = sorted(set(b["date"][:10] for b in bars))
    prev_dates = [d for d in all_dates if d < date_str]
    if not prev_dates: return None
    prev_date = prev_dates[-1]
    prev_bars = [b for b in bars if b["date"][:10] == prev_date]
    if not prev_bars: return None
    
    # === FEATURES ===
    total_vol_today = sum(b.get("volume",0) for b in today_bars)
    total_vol_prev = sum(b.get("volume",0) for b in prev_bars)
    if total_vol_prev == 0 or total_vol_today == 0: return None
    
    # First 5 min (9:00-9:04)
    first5 = [b for b in today_bars if b.get("date","")[11:16] < "09:05"]
    vol_first5 = sum(b.get("volume",0) for b in first5)
    
    # First 15 min
    first15 = [b for b in today_bars if b.get("date","")[11:16] < "09:15"]
    vol_first15 = sum(b.get("volume",0) for b in first15)
    
    # Volume ratios
    vol_ratio_total = total_vol_today / total_vol_prev
    vol_ratio_5min = vol_first5 / total_vol_prev if total_vol_prev > 0 else 0
    vol_conc_5 = vol_first5 / total_vol_today if total_vol_today > 0 else 0
    vol_conc_15 = vol_first15 / total_vol_today if total_vol_today > 0 else 0
    
    # Price direction in first 5 min
    if first5 and first5[0].get("open", 0) > 0:
        price_chg_5min = (first5[-1].get("close",0) - first5[0].get("open",0)) / first5[0].get("open",1)
    else:
        price_chg_5min = 0
    
    # Price direction in first 15 min
    if first15 and first15[0].get("open", 0) > 0:
        price_chg_15min = (first15[-1].get("close",0) - first15[0].get("open",0)) / first15[0].get("open",1)
    else:
        price_chg_15min = 0
    
    # Dollar volume (for absolute size)
    avg_price = np.mean([b.get("close",0) for b in today_bars if b.get("close",0)>0]) if today_bars else 0
    dollar_vol = total_vol_today * avg_price
    
    return {
        "vol_ratio_total": vol_ratio_total,
        "vol_ratio_5min": vol_ratio_5min,
        "vol_conc_5": vol_conc_5,
        "vol_conc_15": vol_conc_15,
        "price_chg_5min": price_chg_5min,
        "price_chg_15min": price_chg_15min,
        "dollar_vol": dollar_vol,
        "total_vol": total_vol_today,
    }

# Process all recent signals
print(f"\nLoading 1-min features...")
t0 = time.time()
results = []
loaded = 0
skipped = 0

for _, row in df_recent.iterrows():
    feats = load_1min_features(row["stock"], row["date"])
    if not feats:
        skipped += 1
        continue
    feats["pnl"] = row["pnl"]
    feats["win"] = row["win"]
    feats["gap"] = abs(row["adj_gap"])
    feats["direction"] = row["direction"]
    feats["mkt_group"] = row["mkt_group"]
    feats["market_ret"] = row["market_ret"]
    feats["date"] = row["date"]
    feats["stock"] = row["stock"]
    results.append(feats)
    loaded += 1
    
    if loaded % 500 == 0:
        print(f"  {loaded} loaded, {skipped} skipped, {time.time()-t0:.0f}s")

print(f"\nDone: {loaded} loaded, {skipped} skipped in {time.time()-t0:.0f}s")

if results:
    rdf = pd.DataFrame(results)
    rdf.to_csv(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\vol_features.csv", index=False)
    print(f"Saved: vol_features.csv")
    
    # === ANALYSIS ===
    print(f"\n{'='*60}")
    print(f"  BASELINE BY MARKET CONDITION")
    print(f"{'='*60}")
    for grp in ["MKT_FLAT", "MKT_UP", "MKT_DOWN"]:
        sub = rdf[rdf["mkt_group"]==grp]
        if len(sub)>0:
            print(f"  {grp:>10}: {len(sub):>5} signals, WR={sub['win'].mean()*100:.1f}%, avg={sub['pnl'].mean()*100:.2f}%")
