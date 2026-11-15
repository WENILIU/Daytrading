# -*- coding: utf-8 -*-
r"""U3: Amplitude (high-low/close) and U2: Turnover/volume ratio vs gap fade P&L.

U3 hypothesis: high recent amplitude = more room to fade = better gap fade.
U2 hypothesis: high turnover = more retail participation = more extreme mispricing.

Uses price_high/low/close for amplitude, vol_ratio (already in signals) for U2.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
from scipy import stats

sig = pd.read_pickle("signals_v13.pkl")
sig["date"] = pd.to_datetime(sig["date"])
short = sig[sig["direction"] == "SHORT"].copy()
print(f"SHORT signals: {len(short):,}")

# --- U3: Compute 5-day average amplitude from price data ---
print("Loading price data for amplitude...")
finlab = r"D:\AI專案\StockAgent\finlab\database"
hi = pd.DataFrame(pd.read_pickle(f"{finlab}\\price_high.pkl"))
lo = pd.DataFrame(pd.read_pickle(f"{finlab}\\price_low.pkl"))
cl = pd.DataFrame(pd.read_pickle(f"{finlab}\\price_close.pkl"))
for df in (hi, lo, cl):
    df.index = pd.to_datetime(df.index)

# amplitude = (high - low) / close, per day
amplitude = (hi - lo) / cl
# 5-day rolling mean of amplitude (shifted by 1 to avoid look-ahead)
amp5 = amplitude.rolling(5).mean().shift(1)
print(f"Amplitude panel: {amp5.shape}")

# Join: for each signal, get the stock's amp5 value on the signal date
# Vectorized: build a lookup
print("Joining amplitude to signals...")
# Get unique stocks and dates
stocks = short["stock"].unique()
dates = short["date"].unique()
# For memory efficiency, only keep columns for stocks in our signals
stock_cols = [s for s in stocks if s in amp5.columns]
print(f"  Stocks in panel: {len(stock_cols)}/{len(stocks)}")
amp_sub = amp5[stock_cols]

# Merge: for each (date, stock), look up amp5
short["amp5"] = np.nan
for dt in dates:
    if dt not in amp_sub.index:
        continue
    row = amp_sub.loc[dt]
    mask = short["date"] == dt
    stocks_at_dt = short.loc[mask, "stock"].values
    vals = row.reindex(stocks_at_dt).values
    short.loc[mask, "amp5"] = vals

valid_amp = short.dropna(subset=["amp5"])
print(f"  Joined: {len(valid_amp):,} signals with amplitude data")

# --- U3 test ---
print("\n" + "="*70)
print("U3: 5-day average amplitude vs SHORT P&L")
print("="*70)
q = valid_amp["amp5"].quantile([0.2, 0.4, 0.6, 0.8]).values
bins_a = [-np.inf] + list(q) + [np.inf]
labels_a = ["Q1(lowest)", "Q2", "Q3", "Q4", "Q5(highest)"]
valid_amp["amp_bucket"] = pd.cut(valid_amp["amp5"], bins=bins_a, labels=labels_a)
print(f"{'Amplitude quintile':<18} {'n':>8} {'mean P&L':>10} {'median':>10} {'win%':>7} {'amp range'}")
print("-"*75)
for i, label in enumerate(labels_a):
    g = valid_amp[valid_amp["amp_bucket"] == label]
    p = g["p"]
    amp_range = f"{g['amp5'].min()*100:.1f}~{g['amp5'].max()*100:.1f}%"
    if len(p) < 10: continue
    print(f"{label:<18} {len(p):>8,} {p.mean()*100:>+9.3f}% {p.median()*100:>+9.3f}% {(p>0).mean()*100:>6.1f}% {amp_range}")

# Statistical test: top quintile vs bottom
top = valid_amp[valid_amp["amp_bucket"] == "Q5(highest)"]["p"]
bot = valid_amp[valid_amp["amp_bucket"] == "Q1(lowest)"]["p"]
t, pval = stats.ttest_ind(top, bot, equal_var=False)
print(f"\n  Q5 vs Q1: diff={(top.mean()-bot.mean())*100:+.3f}%, t={t:.3f}, p={pval:.2e}")

# --- U2: vol_ratio (volume vs 20-day average) ---
print("\n" + "="*70)
print("U2: Volume ratio (vol_ratio, today vs 20d avg) vs SHORT P&L")
print("="*70)
bins_v = [-np.inf, 0.5, 1.0, 2.0, 4.0, 8.0, np.inf]
labels_v = ["<0.5x", "0.5-1x", "1-2x", "2-4x", "4-8x", ">8x"]
short["vol_bucket"] = pd.cut(short["vol_ratio"], bins=bins_v, labels=labels_v)
print(f"{'vol_ratio':<10} {'n':>8} {'mean P&L':>10} {'median':>10} {'win%':>7}")
print("-"*50)
for label in labels_v:
    g = short[short["vol_bucket"] == label]["p"]
    if len(g) < 10: continue
    print(f"{label:<10} {len(g):>8,} {g.mean()*100:>+9.3f}% {g.median()*100:>+9.3f}% {(g>0).mean()*100:>6.1f}%")

# --- U2b: prev_turnover (absolute dollar volume) ---
print("\n" + "="*70)
print("U2b: Previous day turnover (10k TWD) vs SHORT P&L")
print("="*70)
short["turnover_wan"] = short["prev_turnover"] / 10000  # convert to 萬
q2 = short["turnover_wan"].quantile([0.2, 0.4, 0.6, 0.8]).values
bins_t = [-np.inf] + list(q2) + [np.inf]
labels_t = ["Q1(lowest)", "Q2", "Q3", "Q4", "Q5(highest)"]
short["turn_bucket"] = pd.cut(short["turnover_wan"], bins=bins_t, labels=labels_t)
print(f"{'Turnover quintile':<18} {'n':>8} {'mean P&L':>10} {'median':>10} {'win%':>7} {'range(萬)'}")
print("-"*75)
for label in labels_t:
    g = short[short["turn_bucket"] == label]
    p = g["p"]
    rng = f"{g['turnover_wan'].min():.0f}~{g['turnover_wan'].max():.0f}"
    if len(p) < 10: continue
    print(f"{label:<18} {len(p):>8,} {p.mean()*100:>+9.3f}% {p.median()*100:>+9.3f}% {(p>0).mean()*100:>6.1f}% {rng}")

# --- Recent window for both ---
print("\n" + "="*70)
print("Recent (2022-2026) - U3 amplitude")
print("="*70)
recent_amp = valid_amp[valid_amp["date"].dt.year >= 2022]
for label in labels_a:
    g = recent_amp[recent_amp["amp_bucket"] == label]["p"]
    if len(g) < 10: continue
    print(f"  {label:<18} n={len(g):>7,} mean={g.mean()*100:+.3f}% win={(g>0).mean()*100:.1f}%")

print("\n" + "="*70)
print("Recent (2022-2026) - U2 vol_ratio")
print("="*70)
recent_s = short[short["date"].dt.year >= 2022]
for label in labels_v:
    g = recent_s[recent_s["vol_bucket"] == label]["p"]
    if len(g) < 10: continue
    print(f"  {label:<10} n={len(g):>7,} mean={g.mean()*100:+.3f}% win={(g>0).mean()*100:.1f}%")

# --- Incremental over pred_q ---
print("\n" + "="*70)
print("Incremental (pred_q>=0.20) - U3 amplitude")
print("="*70)
traded_amp = valid_amp[valid_amp["pred_q"] >= 0.20]
for label in labels_a:
    g = traded_amp[traded_amp["amp_bucket"] == label]["p"]
    if len(g) < 10: continue
    print(f"  {label:<18} n={len(g):>7,} mean={g.mean()*100:+.3f}%")

print("\n" + "="*70)
print("Incremental (pred_q>=0.20) - U2 vol_ratio")
print("="*70)
traded_v = short[short["pred_q"] >= 0.20]
for label in labels_v:
    g = traded_v[traded_v["vol_bucket"] == label]["p"]
    if len(g) < 10: continue
    print(f"  {label:<10} n={len(g):>7,} mean={g.mean()*100:+.3f}%")

# --- Correlations ---
print("\n" + "="*70)
print("Spearman correlations with SHORT P&L")
print("="*70)
r1, p1 = stats.spearmanr(valid_amp["amp5"], valid_amp["p"])
print(f"  amp5:      rho={r1:+.4f}, p={p1:.2e}, n={len(valid_amp):,}")
r2, p2 = stats.spearmanr(short["vol_ratio"], short["p"])
print(f"  vol_ratio: rho={r2:+.4f}, p={p2:.2e}, n={len(short):,}")
r3, p3 = stats.spearmanr(short["prev_turnover"], short["p"])
print(f"  turnover:  rho={r3:+.4f}, p={p3:.2e}, n={len(short):,}")

print("\nDone.")
