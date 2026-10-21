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

def load_1min_features(stock, date):
    """Load 1-min data and extract volume features for target date."""
    folder = INDEX.get(stock)
    if not folder: return None
    ym = date.strftime("%Y-%m")
    fpath = Path(folder) / f"{stock}_{ym}.json"
    if not fpath.exists(): return None
    
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except: return None
    
    if not isinstance(raw, dict) or "data" not in raw: return None
    bars = raw["data"]
    
    # Group bars by date
    date_str = date.strftime("%Y-%m-%d")
    today_bars = [b for b in bars if b.get("date","").startswith(date_str)]
    if not today_bars: return None
    
    # Previous trading day bars
    prev_dates = sorted(set(b["date"][:10] for b in bars if b["date"][:10] < date_str))
    if not prev_dates: return None
    prev_date = prev_dates[-1]
    prev_bars = [b for b in bars if b["date"][:10] == prev_date]
    if not prev_bars: return None
    
    # Today features
    total_vol_today = sum(b.get("volume",0) for b in today_bars)
    total_vol_prev = sum(b.get("volume",0) for b in prev_bars)
    if total_vol_prev == 0: return None
    
    # First 5 min volume (9:00-9:04)
    first5 = [b for b in today_bars if "09:0" in b.get("date","")[11:16]]
    vol_first5 = sum(b.get("volume",0) for b in first5)
    
    # First 15 min volume
    first15 = [b for b in today_bars if b.get("date","")[11:16] < "09:15"]
    vol_first15 = sum(b.get("volume",0) for b in first15)
    
    # Volume concentration: first5 / total
    vol_conc_5 = vol_first5 / total_vol_today if total_vol_today > 0 else 0
    vol_conc_15 = vol_first15 / total_vol_today if total_vol_today > 0 else 0
    
    # Volume ratio vs yesterday
    vol_ratio = total_vol_today / total_vol_prev
    
    # First 5 min: price direction (open vs close of first 5 min)
    if first5:
        first_bar = first5[0]
        last_first5 = first5[-1]
        price_change_5min = (last_first5.get("close",0) - first_bar.get("open",0)) / first_bar.get("open",1) if first_bar.get("open",0) > 0 else 0
    else:
        price_change_5min = 0
    
    return {
        "vol_ratio": vol_ratio,
        "vol_conc_5": vol_conc_5,
        "vol_conc_15": vol_conc_15,
        "vol_first5": vol_first5,
        "total_vol": total_vol_today,
        "price_change_5min": price_change_5min,
    }

# Target: market>2% SHORT
target = df[(df["market_ret"] > 0.02) & (df["direction"] == "SHORT")].copy()
print(f"Target: {len(target)} SHORT signals in market>2%")
print("Loading 1-min features...")

t0 = time.time()
results = []
for _, row in target.iterrows():
    feats = load_1min_features(row["stock"], row["date"])
    if not feats: continue
    feats["pnl"] = row["pnl"]
    feats["win"] = row["win"]
    feats["gap"] = abs(row["adj_gap"])
    results.append(feats)

print(f"Loaded {len(results)} in {time.time()-t0:.1f}s")

if results:
    rdf = pd.DataFrame(results)
    print(f"\nOverall: WR={rdf['win'].mean()*100:.1f}%, avg={rdf['pnl'].mean()*100:.2f}%")
    
    print(f"\n=== Volume Ratio (today/yesterday total) ===")
    for lo, hi, label in [(0,0.5,"<0.5x"),(0.5,1.0,"0.5-1x"),(1.0,2.0,"1-2x"),
                          (2.0,3.0,"2-3x"),(3.0,5.0,"3-5x"),(5.0,999,">5x")]:
        sub = rdf[(rdf["vol_ratio"]>=lo)&(rdf["vol_ratio"]<hi)]
        if len(sub)>=5:
            print(f"  {label:>7}: {len(sub):>3} signals, WR={sub['win'].mean()*100:.1f}%, avg={sub['pnl'].mean()*100:.2f}%")
    
    print(f"\n=== Volume Concentration (first 5min / total) ===")
    for lo, hi, label in [(0,0.05,"<5%"),(0.05,0.10,"5-10%"),(0.10,0.20,"10-20%"),
                          (0.20,0.35,"20-35%"),(0.35,0.50,"35-50%"),(0.50,1.0,">50%")]:
        sub = rdf[(rdf["vol_conc_5"]>=lo)&(rdf["vol_conc_5"]<hi)]
        if len(sub)>=5:
            print(f"  {label:>7}: {len(sub):>3} signals, WR={sub['win'].mean()*100:.1f}%, avg={sub['pnl'].mean()*100:.2f}%")
    
    print(f"\n=== First 5min Price Direction ===")
    for lo, hi, label in [(-99,-0.03,"drop>3%"),(-0.03,-0.01,"drop1-3%"),(-0.01,0,"drop0-1%"),
                          (0,0.01,"up0-1%"),(0.01,0.03,"up1-3%"),(0.03,99,"up>3%")]:
        sub = rdf[(rdf["price_change_5min"]>=lo)&(rdf["price_change_5min"]<hi)]
        if len(sub)>=5:
            print(f"  {label:>9}: {len(sub):>3} signals, WR={sub['win'].mean()*100:.1f}%, avg={sub['pnl'].mean()*100:.2f}%")
    
    print(f"\n=== COMBO: Price drop + Volume concentration ===")
    # Best combo: price dropped + volume NOT concentrated in first 5min
    combo1 = rdf[(rdf["price_change_5min"] < -0.01) & (rdf["vol_conc_5"] < 0.20)]
    combo2 = rdf[(rdf["price_change_5min"] < -0.01) & (rdf["vol_conc_5"] >= 0.20)]
    combo3 = rdf[(rdf["price_change_5min"] >= 0) & (rdf["vol_conc_5"] >= 0.35)]
    if len(combo1)>=5:
        print(f"  Drop>1% + vol<20% (slow fade): {len(combo1):>3}, WR={combo1['win'].mean()*100:.1f}%, avg={combo1['pnl'].mean()*100:.2f}%")
    if len(combo2)>=5:
        print(f"  Drop>1% + vol>20% (fast dump): {len(combo2):>3}, WR={combo2['win'].mean()*100:.1f}%, avg={combo2['pnl'].mean()*100:.2f}%")
    if len(combo3)>=5:
        print(f"  Up + vol>35% (gap&go):     {len(combo3):>3}, WR={combo3['win'].mean()*100:.1f}%, avg={combo3['pnl'].mean()*100:.2f}%")
