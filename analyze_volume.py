"""
Load 1-min K data for market>2% SHORT signals.
Check if volume features can improve win rate.
"""
import pandas as pd
import numpy as np
import json, os, time
from pathlib import Path
"""
Analyze volume features vs win rate for Gap Fade SHORT signals.
Focus: improve 'flat' market SHORT WR from 60% -> 80%+
"""
import pandas as pd, numpy as np

df = pd.read_csv('volume_features.csv', parse_dates=['date'])
print(f"Total features: {len(df)}")
print(f"Directions: {df['direction'].value_counts().to_dict()}")
print(f"Market conditions: {df['mkt_cond'].value_counts().to_dict()}")
print()

# Focus on SHORT signals by market condition
short = df[df['direction']=='SHORT'].copy()
print("=== SHORT by market condition ===")
for cond in ['up2','flat','down2']:
    sub = short[short['mkt_cond']==cond]
    if len(sub)==0: continue
    wr = sub['win'].mean()*100
    pnl = sub['pnl'].mean()*100
    print(f"  {cond}: {len(sub)} signals, WR={wr:.1f}%, avg PnL={pnl:+.2f}%")
print()

# Feature analysis for 'flat' SHORT
flat = short[short['mkt_cond']=='flat'].copy()
base_wr = flat['win'].mean()*100
print(f"=== FLAT SHORT: {len(flat)} signals, WR={base_wr:.1f}% ===")
print()

# 1. Price change 5min
print("--- price_chg_5min (SHORT: price dropping = good) ---")
bins5 = [-1,-0.03,-0.01,0,0.01,0.03,1]
labels5 = ['drop>3%','drop1-3%','drop0-1%','rise0-1%','rise1-3%','rise>3%']
flat['pc5_bin'] = pd.cut(flat['price_chg_5min'], bins=bins5, labels=labels5)
for b in labels5:
    sub = flat[flat['pc5_bin']==b]
    if len(sub)>0:
        wr = sub['win'].mean()*100
        pnl = sub['pnl'].mean()*100
        print(f"  {b:12s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")
print()

# 2. Volume concentration 5min
print("--- vol_conc_5 (first 5min / total day) ---")
bins_c = [0,0.1,0.2,0.3,0.5,1.0]
labels_c = ['<10%','10-20%','20-30%','30-50%','>50%']
flat['vc_bin'] = pd.cut(flat['vol_conc_5'], bins=bins_c, labels=labels_c)
for b in labels_c:
    sub = flat[flat['vc_bin']==b]
    if len(sub)>0:
        wr = sub['win'].mean()*100
        pnl = sub['pnl'].mean()*100
        print(f"  {b:8s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")
print()

# 3. Volume ratio (today/prev)
print("--- vol_ratio (today/prev day volume) ---")
bins_r = [0,0.5,1.0,1.5,2.0,3.0,100]
labels_r = ['<0.5x','0.5-1x','1-1.5x','1.5-2x','2-3x','>3x']
flat['vr_bin'] = pd.cut(flat['vol_ratio'], bins=bins_r, labels=labels_r)
for b in labels_r:
    sub = flat[flat['vr_bin']==b]
    if len(sub)>0:
        wr = sub['win'].mean()*100
        pnl = sub['pnl'].mean()*100
        print(f"  {b:8s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")
print()

# 4. Price change 15min
print("--- price_chg_15min ---")
bins15 = [-1,-0.03,-0.01,0,0.01,0.03,1]
labels15 = ['drop>3%','drop1-3%','drop0-1%','rise0-1%','rise1-3%','rise>3%']
flat['pc15_bin'] = pd.cut(flat['price_chg_15min'], bins=bins15, labels=labels15)
for b in labels15:
    sub = flat[flat['pc15_bin']==b]
    if len(sub)>0:
        wr = sub['win'].mean()*100
        pnl = sub['pnl'].mean()*100
        print(f"  {b:12s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")
print()

# 5. COMBINATIONS - the key insight
print("=== COMBINATIONS (price + volume) ===")

# Price dropped + volume NOT concentrated = real reversal
cond1 = (flat['price_chg_5min'] < -0.01) & (flat['vol_conc_5'] < 0.3)
sub = flat[cond1]
if len(sub)>0:
    wr = sub['win'].mean()*100
    pnl = sub['pnl'].mean()*100
    print(f"  Price drop>1% + vol_conc<30%: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")

# Price dropped + volume concentrated = gap and go (bad)
cond2 = (flat['price_chg_5min'] < -0.01) & (flat['vol_conc_5'] >= 0.3)
sub = flat[cond2]
if len(sub)>0:
    wr = sub['win'].mean()*100
    pnl = sub['pnl'].mean()*100
    print(f"  Price drop>1% + vol_conc>=30%: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")

# Price rising + volume low = weak momentum (still good for SHORT)
cond3 = (flat['price_chg_5min'] >= 0) & (flat['vol_conc_5'] < 0.15)
sub = flat[cond3]
if len(sub)>0:
    wr = sub['win'].mean()*100
    pnl = sub['pnl'].mean()*100
    print(f"  Price rise + vol_conc<15%:     {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")

# Price rising + volume high = strong momentum (bad for SHORT)
cond4 = (flat['price_chg_5min'] >= 0) & (flat['vol_conc_5'] >= 0.3)
sub = flat[cond4]
if len(sub)>0:
    wr = sub['win'].mean()*100
    pnl = sub['pnl'].mean()*100
    print(f"  Price rise + vol_conc>=30%:    {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")

# Strict filter: price drop + low concentration + moderate vol ratio
cond5 = (flat['price_chg_5min'] < -0.01) & (flat['vol_conc_5'] < 0.2) & (flat['vol_ratio'] < 3.0)
sub = flat[cond5]
if len(sub)>0:
    wr = sub['win'].mean()*100
    pnl = sub['pnl'].mean()*100
    print(f"  STRICT: drop>1%+conc<20%+vr<3x: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")

# REJECT: price rising + high vol concentration
cond6 = (flat['price_chg_5min'] >= 0.01) & (flat['vol_conc_5'] >= 0.3)
sub = flat[cond6]
if len(sub)>0:
    wr = sub['win'].mean()*100
    pnl = sub['pnl'].mean()*100
    print(f"  REJECT: rise>1%+conc>=30%:     {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")

print()
print("=== SUMMARY: Best filter for FLAT SHORT ===")
# What if we only take signals where price dropped in first 5min?
good = flat[flat['price_chg_5min'] < -0.005]
bad = flat[flat['price_chg_5min'] >= -0.005]
print(f"  TAKE (drop>0.5%): {len(good)} signals, WR={good['win'].mean()*100:.1f}%, PnL={good['pnl'].mean()*100:+.2f}%")
print(f"  SKIP (else):      {len(bad)} signals, WR={bad['win'].mean()*100:.1f}%, PnL={bad['pnl'].mean()*100:+.2f}%")
print(f"  Impact: skip {len(bad)} trades, keep {len(good)} with WR {good['win'].mean()*100:.1f}%")
DATA_DIR = Path(r"D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線")

# Load signals
df = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")
df["date"] = pd.to_datetime(df["date"])

def simulate_pnl(row, sl=0.06, tp=0.04, cost=0.0017):
    entry = row["entry"]; direction = row["direction"]
    hi = row["day_high"]; lo = row["day_low"]; cl = row["day_close"]
    if direction == "SHORT":
        sl_p = entry*(1+sl); tp_p = entry*(1-tp)
        if hi >= sl_p: exit_p = sl_p
        elif lo <= tp_p: exit_p = tp_p
        else: exit_p = cl
        return (entry-exit_p)/entry - 2*cost
    else:
        sl_p = entry*(1-sl); tp_p = entry*(1+tp)
        if lo <= sl_p: exit_p = sl_p
        elif hi >= tp_p: exit_p = tp_p
        else: exit_p = cl
        return (exit_p-entry)/entry - 2*cost

df["pnl"] = df.apply(simulate_pnl, axis=1)
df["win"] = (df["pnl"] > 0).astype(int)

# Target: market>2% SHORT (the weak subset)
target = df[(df["market_ret"] > 0.02) & (df["direction"] == "SHORT")].copy()
print(f"Target: {len(target)} SHORT signals in market>2%")

# Load daily K-line data for these stocks (has volume)
# Use monthly JSON files
def load_daily_volume(stock, year_month):
    """Load daily K data for a stock-month."""
    # Find the stock folder
    for market_dir in DATA_DIR.iterdir():
        if not market_dir.is_dir(): continue
        stock_dir = market_dir / "1"
        if not stock_dir.exists(): continue
        pattern = f"{stock}_{year_month}.json"
        f = stock_dir / pattern
        if f.exists():
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except:
                pass
    return None

# Sample: load volume for 200 most recent signals
target_sorted = target.sort_values("date", ascending=False).head(200)
print(f"Loading volume for {len(target_sorted)} signals...")

results = []
t0 = time.time()
loaded = 0

for _, row in target_sorted.iterrows():
    stock = row["stock"]
    date = row["date"]
    ym = date.strftime("%Y-%m")
    
    daily_data = load_daily_volume(stock, ym)
    if not daily_data:
        continue
    
    # Find the target date and previous day
    target_date_str = date.strftime("%Y-%m-%d")
    target_idx = None
    for i, d in enumerate(daily_data):
        if d.get("date", "") == target_date_str:
            target_idx = i
            break
    
    if target_idx is None or target_idx == 0:
        continue
    
    today = daily_data[target_idx]
    yesterday = daily_data[target_idx - 1]
    
    today_vol = today.get("volume", 0)
    today_amount = today.get("amount", 0) or today_vol * today.get("close", 0)
    y_vol = yesterday.get("volume", 0)
    y_amount = yesterday.get("amount", 0) or y_vol * yesterday.get("close", 0)
    
    if y_vol == 0:
        continue
    
    vol_ratio = today_vol / y_vol  # today volume vs yesterday
    loaded += 1
    
    results.append({
        "date": date, "stock": stock, "pnl": row["pnl"], "win": row["win"],
        "adj_gap": row["adj_gap"], "vol_ratio": vol_ratio,
        "today_vol": today_vol, "y_vol": y_vol,
    })
    
    if loaded >= 150:
        break

elapsed = time.time() - t0
print(f"Loaded {loaded} in {elapsed:.1f}s")

if results:
    rdf = pd.DataFrame(results)
    
    print(f"\n=== Volume Ratio vs Win Rate (SHORT, market>2%) ===")
    print(f"Overall: {len(rdf)} signals, WR={rdf['win'].mean()*100:.1f}%")
    
    # Volume ratio buckets
    for lo, hi, label in [(0, 0.5, "<0.5x"), (0.5, 1.0, "0.5-1x"), 
                          (1.0, 2.0, "1-2x"), (2.0, 3.0, "2-3x"),
                          (3.0, 5.0, "3-5x"), (5.0, 999, ">5x")]:
        sub = rdf[(rdf["vol_ratio"] >= lo) & (rdf["vol_ratio"] < hi)]
        if len(sub) >= 5:
            print(f"  Vol {label:>6}: {len(sub):>3} signals, WR={sub['win'].mean()*100:.1f}%, avg={sub['pnl'].mean()*100:.2f}%")
