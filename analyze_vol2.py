import pandas as pd, numpy as np, json, time
from pathlib import Path

# Load index
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

def load_volume(stock, date):
    """Load daily volume for stock on date, plus previous days."""
    folder = INDEX.get(stock)
    if not folder: return None
    ym = date.strftime("%Y-%m")
    fpath = Path(folder) / f"{stock}_{ym}.json"
    if not fpath.exists(): return None
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except: return None
    
    target_str = date.strftime("%Y-%m-%d")
    for i, d in enumerate(data):
        if d.get("date","") == target_str and i > 0:
            return {"today": d, "yesterday": data[i-1], "prev2": data[i-2] if i>=2 else None}
    return None

# Target: market>2% SHORT
target = df[(df["market_ret"] > 0.02) & (df["direction"] == "SHORT")].copy()
print(f"Target: {len(target)} SHORT signals in market>2%")

# Load volume for ALL targets (should be fast with index)
t0 = time.time()
results = []
for _, row in target.iterrows():
    vol_data = load_volume(row["stock"], row["date"])
    if not vol_data: continue
    
    today = vol_data["today"]
    yesterday = vol_data["yesterday"]
    
    t_vol = today.get("volume", 0)
    t_amt = today.get("amount", 0) or t_vol * today.get("close", 0)
    y_vol = yesterday.get("volume", 0)
    y_amt = yesterday.get("amount", 0) or y_vol * yesterday.get("close", 0)
    
    if y_vol == 0 or t_vol == 0: continue
    
    vol_ratio = t_vol / y_vol
    amt_ratio = t_amt / y_amt if y_amt > 0 else 0
    
    # Also compute: gap size relative to volume
    gap = abs(row["adj_gap"])
    
    results.append({
        "date": row["date"], "stock": row["stock"], "pnl": row["pnl"], "win": row["win"],
        "gap": gap, "vol_ratio": vol_ratio, "amt_ratio": amt_ratio,
        "t_vol": t_vol, "y_vol": y_vol, "t_amt": t_amt,
    })

print(f"Loaded {len(results)} in {time.time()-t0:.1f}s")

if results:
    rdf = pd.DataFrame(results)
    
    print(f"\n=== Volume Ratio vs Win Rate (SHORT, market>2%) ===")
    print(f"Overall: {len(rdf)} signals, WR={rdf['win'].mean()*100:.1f}%, avg={rdf['pnl'].mean()*100:.2f}%")
    
    print(f"\n--- Volume Ratio (today/yesterday) ---")
    for lo, hi, label in [(0,0.5,"<0.5x"),(0.5,1.0,"0.5-1x"),(1.0,1.5,"1-1.5x"),
                          (1.5,2.0,"1.5-2x"),(2.0,3.0,"2-3x"),(3.0,5.0,"3-5x"),(5.0,999,">5x")]:
        sub = rdf[(rdf["vol_ratio"]>=lo)&(rdf["vol_ratio"]<hi)]
        if len(sub)>=5:
            print(f"  {label:>7}: {len(sub):>3} signals, WR={sub['win'].mean()*100:.1f}%, avg={sub['pnl'].mean()*100:.2f}%")
    
    print(f"\n--- Dollar Volume (absolute) ---")
    for lo, hi, label in [(0,5e7,"<50M"),(5e7,2e8,"50-200M"),(2e8,1e9,"200M-1B"),(1e9,99e9,">1B")]:
        sub = rdf[(rdf["t_amt"]>=lo)&(rdf["t_amt"]<hi)]
        if len(sub)>=5:
            print(f"  {label:>8}: {len(sub):>3} signals, WR={sub['win'].mean()*100:.1f}%, avg={sub['pnl'].mean()*100:.2f}%")
    
    print(f"\n--- Gap Size x Volume Ratio (interaction) ---")
    for g_lo, g_hi, g_label in [(0.05,0.07,"5-7%"),(0.07,0.99,">7%")]:
        for v_lo, v_hi, v_label in [(0,1.5,"vol<1.5x"),(1.5,999,"vol>1.5x")]:
            sub = rdf[(rdf["gap"]>=g_lo)&(rdf["gap"]<g_hi)&(rdf["vol_ratio"]>=v_lo)&(rdf["vol_ratio"]<v_hi)]
            if len(sub)>=5:
                print(f"  Gap {g_label} + {v_label}: {len(sub):>3} signals, WR={sub['win'].mean()*100:.1f}%, avg={sub['pnl'].mean()*100:.2f}%")
