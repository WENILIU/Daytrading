# -*- coding: utf-8 -*-
r"""Strategy-level test: enter at 09:03 only after price confirms falling.

For shorts, if we enter at 09:03 instead of 09:00:
  new_p = p + price_dir_3min
  (price_dir_3min < 0 means price fell -> we miss that profit -> new_p < p)
  (price_dir_3min > 0 means price rose -> we get a better entry -> new_p > p)

Compare:
  A) Current: trade all at 09:00, P&L = p
  B) Confirmed: only trade when price_dir_3min < threshold, P&L = p + price_dir_3min
  C) Confirmed + skip rising: only trade when price falling, skip when rising

Also test different thresholds to find the optimal confirmation level.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os, json
from scipy import stats
from collections import defaultdict

DATA_PATH = r"D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線"

sig = pd.read_pickle("signals_v13.pkl")
sig["date"] = pd.to_datetime(sig["date"])
short = sig[(sig["direction"] == "SHORT") & (sig["date"] >= "2023-05-01") & (sig["date"] <= "2026-01-31")].copy()
short["stock_str"] = short["stock"].astype(str)

# Build stock->dir index
stock_dir = {}
for d in os.listdir(DATA_PATH):
    dp = os.path.join(DATA_PATH, d, "1")
    if not os.path.isdir(dp): continue
    files = os.listdir(dp)
    if not files: continue
    code = files[0].split("_")[0]
    if code.isdigit() and len(code) == 4:
        stock_dir[code] = dp

# Extract opening data (same as before but also get the 09:03 price for entry adjustment)
short["month"] = short["date"].dt.strftime("%Y-%m")
groups = short.groupby(["stock_str", "month"])

results = []
for (stock, month), grp in groups:
    if stock not in stock_dir: continue
    fpath = os.path.join(stock_dir[stock], f"{stock}_{month}.json")
    if not os.path.exists(fpath): continue
    try:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
    except: continue
    bars = data.get("data", [])
    if not bars: continue
    day_bars = defaultdict(list)
    for b in bars:
        day_bars[b["date"][:10]].append(b)

    for _, row in grp.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d")
        if date_str not in day_bars: continue
        day = sorted(day_bars[date_str], key=lambda x: x["date"])
        open_bars = [b for b in day if "T09:0" in b["date"] and b["date"][11:16] <= "09:03"]
        if len(open_bars) < 2: continue
        open_price = open_bars[0]["open"]
        price_0903 = open_bars[-1]["close"]
        vol_3min = sum(b["volume"] for b in open_bars)
        price_dir = (price_0903 - open_price) / open_price if open_price > 0 else 0
        results.append({
            "date": row["date"], "stock": stock, "p": row["p"],
            "pred_q": row["pred_q"], "adj_gap": row["adj_gap"],
            "price_dir_3min": price_dir, "vol_3min": vol_3min,
            "open_price": open_price, "price_0903": price_0903
        })

df = pd.DataFrame(results)
print(f"Signals with 1-min data: {len(df):,}")

# Adjusted P&L if entering at 09:03 instead of 09:00
# For shorts: new_p = p + price_dir_3min (miss the move from open to 09:03)
df["p_0903"] = df["p"] + df["price_dir_3min"]

# --- Strategy comparison ---
print("\n" + "="*70)
print("STRATEGY COMPARISON (all signals with 1-min data)")
print("="*70)
print(f"{'Strategy':<40} {'n':>6} {'mean P&L':>10} {'total':>10} {'win%':>7}")
print("-"*78)

# A: Current (enter at 09:00, trade all)
a = df["p"]
print(f"{'A: 09:00 全部進場（現行）':<40} {len(a):>6,} {a.mean()*100:>+9.3f}% {a.sum()*100:>+9.1f}% {(a>0).mean()*100:>6.1f}%")

# B: Enter at 09:03, trade all (no filter, just delayed entry)
b = df["p_0903"]
print(f"{'B: 09:03 全部進場（無確認，純延遲）':<40} {len(b):>6,} {b.mean()*100:>+9.3f}% {b.sum()*100:>+9.1f}% {(b>0).mean()*100:>6.1f}%")

# C: Enter at 09:03, only if price falling (confirmation filter)
for threshold in [0, -0.002, -0.005, -0.01, -0.015, -0.02]:
    mask = df["price_dir_3min"] < threshold
    c = df[mask]["p_0903"]
    skipped = df[~mask]["p"]
    label = f"C: 09:03 確認跌>{abs(threshold)*100:.1f}%才進"
    if len(c) < 10: continue
    print(f"{label:<40} {len(c):>6,} {c.mean()*100:>+9.3f}% {c.sum()*100:>+9.1f}% {(c>0).mean()*100:>6.1f}%")
    print(f"{'  (skipped: n=' + str(len(skipped)) + ' would-have-been mean=' + f'{skipped.mean()*100:+.3f}%' + ')':<40}")

# D: Only trade when price falling AND pred_q >= 0.20 (model + confirmation)
print()
for threshold in [0, -0.005, -0.01]:
    mask = (df["price_dir_3min"] < threshold) & (df["pred_q"] >= 0.20)
    d = df[mask]["p_0903"]
    if len(d) < 10: continue
    label = f"D: 確認跌>{abs(threshold)*100:.1f}% + pred_q>=0.20"
    print(f"{label:<40} {len(d):>6,} {d.mean()*100:>+9.3f}% {d.sum()*100:>+9.1f}% {(d>0).mean()*100:>6.1f}%")

# --- Key metrics ---
print("\n" + "="*70)
print("KEY METRICS COMPARISON")
print("="*70)

# Current strategy (A)
a_mean = a.mean()
a_std = a.std()
a_sharpe = a_mean / a_std * np.sqrt(252) if a_std > 0 else 0

# Best confirmed strategy (C with threshold=-0.005)
mask_best = df["price_dir_3min"] < -0.005
c_best = df[mask_best]["p_0903"]
c_mean = c_best.mean()
c_std = c_best.std()
c_sharpe = c_mean / c_std * np.sqrt(252) if c_std > 0 else 0

print(f"  A (現行):     mean={a_mean*100:+.3f}%/trade, Sharpe~{a_sharpe:.1f}, n={len(a):,}")
print(f"  C (確認跌>0.5%): mean={c_mean*100:+.3f}%/trade, Sharpe~{c_sharpe:.1f}, n={len(c_best):,}")
print(f"  Improvement: {(c_mean-a_mean)*100:+.3f}%/trade, Sharpe {c_sharpe-a_sharpe:+.1f}")
print(f"  Trade frequency: {len(c_best)/len(a)*100:.1f}% of current (skip {100-len(c_best)/len(a)*100:.1f}%)")

# --- What we're skipping ---
print("\n" + "="*70)
print("What does the confirmation filter skip?")
print("="*70)
skipped = df[df["price_dir_3min"] >= -0.005]
print(f"  Skipped: n={len(skipped):,}")
print(f"  Their P&L (if entered at 09:00): mean={skipped['p'].mean()*100:+.3f}%, win={(skipped['p']>0).mean()*100:.1f}%")
print(f"  Their P&L (if entered at 09:03): mean={skipped['p_0903'].mean()*100:+.3f}%")
print(f"  -> We skip trades that would have been: {skipped['p'].mean()*100:+.3f}% (09:00) or {skipped['p_0903'].mean()*100:+.3f}% (09:03)")

# --- Per-day impact ---
print("\n" + "="*70)
print("Per-day impact (simulating daily P&L)")
print("="*70)
daily_a = df.groupby("date")["p"].sum()
daily_c = df[mask_best].groupby("date")["p_0903"].sum()
# Align dates
all_dates = sorted(set(daily_a.index) | set(daily_c.index))
daily_a_full = pd.Series(0.0, index=all_dates)
daily_c_full = pd.Series(0.0, index=all_dates)
for d, v in daily_a.items(): daily_a_full[d] = v
for d, v in daily_c.items(): daily_c_full[d] = v

print(f"  A (現行): daily mean={daily_a_full.mean()*100:+.4f}%, std={daily_a_full.std()*100:.4f}%, Sharpe={daily_a_full.mean()/daily_a_full.std()*np.sqrt(252):.1f}")
print(f"  C (確認): daily mean={daily_c_full.mean()*100:+.4f}%, std={daily_c_full.std()*100:.4f}%, Sharpe={daily_c_full.mean()/daily_c_full.std()*np.sqrt(252):.1f}")
print(f"  Days with trades: A={len(daily_a):,}, C={len(daily_c):,}")

# Max drawdown of daily cumulative
cum_a = daily_a_full.cumsum()
cum_c = daily_c_full.cumsum()
dd_a = (cum_a - cum_a.cummax()).min()
dd_c = (cum_c - cum_c.cummax()).min()
print(f"  Max drawdown (sum of P&L): A={dd_a*100:.1f}%, C={dd_c*100:.1f}%")

print("\nDone.")
