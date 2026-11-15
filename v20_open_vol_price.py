# -*- coding: utf-8 -*-
r"""U5: Opening volume-price divergence (量價背離) as a confirmation filter.

Hypothesis: at 09:00-09:03, if opening volume is HIGH but price is FALLING,
that is distribution (institutions selling into the gap) -> stronger fade signal.
If volume is high and price is RISING, that is genuine momentum -> skip the short.

Uses 1-minute data (2023-05 to 2026-01, 1784 stocks, ~48k SHORT signals).
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
print(f"Target signals: {len(short):,} SHORT in 1-min data range")

# Build stock -> directory mapping
print("Building stock->dir index...")
stock_dir = {}
for d in os.listdir(DATA_PATH):
    dp = os.path.join(DATA_PATH, d, "1")
    if not os.path.isdir(dp):
        continue
    files = os.listdir(dp)
    if not files:
        continue
    code = files[0].split("_")[0]
    if code.isdigit() and len(code) == 4:
        stock_dir[code] = dp
print(f"  Indexed {len(stock_dir)} stocks")

# Group signals by (stock, month) to minimize file loads
short["month"] = short["date"].dt.strftime("%Y-%m")
groups = short.groupby(["stock_str", "month"])
print(f"  Signal groups (stock x month): {len(groups)}")

# Process each group
results = []
processed = 0
errors = 0
for (stock, month), grp in groups:
    if stock not in stock_dir:
        continue
    fpath = os.path.join(stock_dir[stock], f"{stock}_{month}.json")
    if not os.path.exists(fpath):
        continue
    try:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        errors += 1
        continue
    bars = data.get("data", [])
    if not bars:
        continue
    # Bars are reverse chronological. Group by date.
    day_bars = defaultdict(list)
    for b in bars:
        dt = b["date"][:10]  # YYYY-MM-DD
        day_bars[dt].append(b)

    for _, row in grp.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d")
        if date_str not in day_bars:
            continue
        # Sort bars chronologically
        day = sorted(day_bars[date_str], key=lambda x: x["date"])
        # Find bars from 09:00 to 09:03 (first 4 bars including 09:00)
        open_bars = [b for b in day if "T09:0" in b["date"] and b["date"][11:16] <= "09:03"]
        if len(open_bars) < 2:
            continue
        # Opening price = first bar's open
        open_price = open_bars[0]["open"]
        # Price at 09:03 = last bar in window's close
        price_0903 = open_bars[-1]["close"]
        # Volume in first 3 minutes
        vol_3min = sum(b["volume"] for b in open_bars)
        # Price direction: (price_0903 - open_price) / open_price
        price_dir = (price_0903 - open_price) / open_price if open_price > 0 else 0

        results.append({
            "date": row["date"], "stock": stock, "p": row["p"],
            "pred_q": row["pred_q"], "adj_gap": row["adj_gap"],
            "vol_3min": vol_3min, "price_dir_3min": price_dir,
            "open_price": open_price
        })
        processed += 1
        if processed % 5000 == 0:
            print(f"  Processed {processed:,}...")

print(f"Done: {processed:,} signals with opening data, {errors} file errors")

df = pd.DataFrame(results)
if len(df) == 0:
    print("No data extracted.")
    exit()

# Compute vol_3min as ratio to median vol_3min for that stock (normalize)
vol_median = df.groupby("stock")["vol_3min"].transform("median")
df["vol_ratio_3min"] = df["vol_3min"] / vol_median.replace(0, np.nan)
df = df.dropna(subset=["vol_ratio_3min"])
print(f"Valid for analysis: {len(df):,}")

# --- Classify: volume x price direction ---
vol_high = df["vol_ratio_3min"] > 2.0  # 2x median opening volume
price_down = df["price_dir_3min"] < -0.005  # price fell >0.5% in 3 min
price_up = df["price_dir_3min"] > 0.005

df["category"] = "neutral"
df.loc[vol_high & price_down, "category"] = "HIGH_VOL+PRICE_DOWN(出貨)"
df.loc[vol_high & price_up, "category"] = "HIGH_VOL+PRICE_UP(動能)"
df.loc[~vol_high & price_down, "category"] = "LOW_VOL+PRICE_DOWN"
df.loc[~vol_high & price_up, "category"] = "LOW_VOL+PRICE_UP"

print("\n" + "="*70)
print("U5: Opening volume-price divergence vs SHORT P&L")
print("="*70)
print(f"{'Category':<30} {'n':>7} {'mean P&L':>10} {'median':>10} {'win%':>7}")
print("-"*68)
for cat in ["HIGH_VOL+PRICE_DOWN(出貨)", "HIGH_VOL+PRICE_UP(動能)", "LOW_VOL+PRICE_DOWN", "LOW_VOL+PRICE_UP", "neutral"]:
    g = df[df["category"] == cat]["p"]
    if len(g) < 10: continue
    print(f"{cat:<30} {len(g):>7,} {g.mean()*100:>+9.3f}% {g.median()*100:>+9.3f}% {(g>0).mean()*100:>6.1f}%")

# Statistical test: distribution vs momentum
dist = df[df["category"] == "HIGH_VOL+PRICE_DOWN(出貨)"]["p"]
mom = df[df["category"] == "HIGH_VOL+PRICE_UP(動能)"]["p"]
if len(dist) > 30 and len(mom) > 30:
    t, pval = stats.ttest_ind(dist, mom, equal_var=False)
    print(f"\n  出貨 vs 動能: diff={(dist.mean()-mom.mean())*100:+.3f}%, t={t:.3f}, p={pval:.2e}")

# --- Continuous: price direction in first 3 min ---
print("\n" + "="*70)
print("Continuous: price direction at 09:03 vs SHORT P&L")
print("="*70)
bins_pd = [-np.inf, -0.02, -0.01, -0.005, 0.005, 0.01, 0.02, np.inf]
labels_pd = ["<-2%", "-2~-1%", "-1~-0.5%", "-0.5~+0.5%", "+0.5~1%", "+1~2%", ">2%"]
df["pd_bucket"] = pd.cut(df["price_dir_3min"], bins=bins_pd, labels=labels_pd)
print(f"{'Price dir @09:03':<15} {'n':>7} {'mean P&L':>10} {'win%':>7}")
print("-"*45)
for label in labels_pd:
    g = df[df["pd_bucket"] == label]["p"]
    if len(g) < 10: continue
    print(f"{label:<15} {len(g):>7,} {g.mean()*100:>+9.3f}% {(g>0).mean()*100:>6.1f}%")

# --- Volume ratio continuous ---
print("\n" + "="*70)
print("Continuous: opening volume ratio vs SHORT P&L")
print("="*70)
bins_vr = [-np.inf, 0.5, 1.0, 2.0, 4.0, np.inf]
labels_vr = ["<0.5x", "0.5-1x", "1-2x", "2-4x", ">4x"]
df["vr_bucket"] = pd.cut(df["vol_ratio_3min"], bins=bins_vr, labels=labels_vr)
print(f"{'Vol ratio @open':<15} {'n':>7} {'mean P&L':>10} {'win%':>7}")
print("-"*45)
for label in labels_vr:
    g = df[df["vr_bucket"] == label]["p"]
    if len(g) < 10: continue
    print(f"{label:<15} {len(g):>7,} {g.mean()*100:>+9.3f}% {(g>0).mean()*100:>6.1f}%")

# --- Interaction: high vol + price down (the key hypothesis) ---
print("\n" + "="*70)
print("KEY TEST: High vol (>2x) + price down (<-0.5%) vs everything else")
print("="*70)
key = (df["vol_ratio_3min"] > 2.0) & (df["price_dir_3min"] < -0.005)
other = ~key
print(f"  量價背離(出貨): n={key.sum():,} mean={df[key]['p'].mean()*100:+.3f}% win={(df[key]['p']>0).mean()*100:.1f}%")
print(f"  Other:          n={other.sum():,} mean={df[other]['p'].mean()*100:+.3f}% win={(df[other]['p']>0).mean()*100:.1f}%")
if key.sum() > 30:
    t2, p2 = stats.ttest_ind(df[key]["p"], df[other]["p"], equal_var=False)
    print(f"  t={t2:.3f}, p={p2:.2e}, diff={(df[key]['p'].mean()-df[other]['p'].mean())*100:+.3f}%")

# --- Incremental over pred_q ---
print("\n" + "="*70)
print("Incremental (pred_q>=0.20)")
print("="*70)
traded = df[df["pred_q"] >= 0.20]
key_t = (traded["vol_ratio_3min"] > 2.0) & (traded["price_dir_3min"] < -0.005)
other_t = ~key_t
print(f"  量價背離: n={key_t.sum():,} mean={traded[key_t]['p'].mean()*100:+.3f}%")
print(f"  Other:    n={other_t.sum():,} mean={traded[other_t]['p'].mean()*100:+.3f}%")
if key_t.sum() > 30:
    t3, p3 = stats.ttest_ind(traded[key_t]["p"], traded[other_t]["p"], equal_var=False)
    print(f"  t={t3:.3f}, p={p3:.2e}")

# --- Correlations ---
print("\n" + "="*70)
print("Spearman correlations")
print("="*70)
r1, p1 = stats.spearmanr(df["price_dir_3min"], df["p"])
print(f"  price_dir_3min: rho={r1:+.4f}, p={p1:.2e}, n={len(df):,}")
r2, p2 = stats.spearmanr(df["vol_ratio_3min"], df["p"])
print(f"  vol_ratio_3min: rho={r2:+.4f}, p={p2:.2e}, n={len(df):,}")

print("\nDone.")
