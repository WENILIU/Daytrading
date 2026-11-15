# -*- coding: utf-8 -*-
r"""U1: Does US overnight return predict gap fade P&L?

Hypothesis from 權證小哥: US market rallies big overnight -> TWSE opens big up
-> institutions sell into strength -> SHORT gap fade works better.

Method:
  1. Download S&P 500 daily data (yfinance).
  2. For each TWSE signal date, find the most recent US trading day BEFORE it
     (US closes 05:00 Taipei next day, so the return visible before TWSE opens
     on day D is the US return from US trading day D-1).
  3. Group signals by US return buckets, compare per-trade net P&L.
  4. Check interaction with direction (SHORT vs LONG).
  5. Check if it adds incremental signal after controlling for pred_q.

Only reports measured values with n. No parameter changes.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
import yfinance as yf
from scipy import stats

# --- 1. Load v13 signals ---
sig = pd.read_pickle("signals_v13.pkl")
sig["date"] = pd.to_datetime(sig["date"])
print(f"Signals: {len(sig):,} rows, {sig['date'].min().date()} to {sig['date'].max().date()}")

# --- 2. Download US market data ---
print("Downloading S&P 500...")
sp = yf.download("^GSPC", start="2006-01-01", end="2026-11-01", progress=False)
if isinstance(sp.columns, pd.MultiIndex):
    sp.columns = sp.columns.get_level_values(0)
sp["ret"] = sp["Close"].pct_change()
sp = sp[["ret"]].dropna()
sp.index = pd.to_datetime(sp.index).tz_localize(None)
print(f"S&P 500: {len(sp)} days, {sp.index.min().date()} to {sp.index.max().date()}")

# Also get NASDAQ for comparison
print("Downloading NASDAQ...")
ndx = yf.download("^IXIC", start="2006-01-01", end="2026-11-01", progress=False)
if isinstance(ndx.columns, pd.MultiIndex):
    ndx.columns = ndx.columns.get_level_values(0)
ndx["ret"] = ndx["Close"].pct_change()
ndx = ndx[["ret"]].dropna()
ndx.index = pd.to_datetime(ndx.index).tz_localize(None)

# --- 3. Join: for each TWSE date, get the most recent US return BEFORE it ---
# US market closes at 05:00 Taipei next day, so the return visible before TWSE
# opens on Taipei day D is from US trading day D-1 (or the last US session before D).
us_dates = sp.index.sort_values()
def get_us_ret(twse_date):
    """Most recent US trading day strictly before twse_date."""
    mask = us_dates < twse_date
    if not mask.any():
        return np.nan
    return sp.loc[us_dates[mask][-1], "ret"]

sig["us_ret"] = sig["date"].apply(get_us_ret)
sig["us_ret_ndx"] = sig["date"].apply(lambda d: ndx.loc[ndx.index[ndx.index < d][-1], "ret"] if (ndx.index < d).any() else np.nan)

valid = sig.dropna(subset=["us_ret"]).copy()
print(f"Joined: {len(valid):,} signals with US return data")

# --- 4. Group by US return buckets ---
# Use meaningful thresholds: big down / mild down / flat / mild up / big up
bins = [-np.inf, -0.02, -0.005, 0.005, 0.02, np.inf]
labels = ["US大漲(>2%)", "US小漲(0.5-2%)", "US平(-0.5~0.5%)", "US小跌(-2~-0.5%)", "US大跌(<-2%)"]
valid["us_bucket"] = pd.cut(valid["us_ret"], bins=bins, labels=labels)

print("\n" + "="*70)
print("U1: US overnight return vs gap fade P&L (all signals)")
print("="*70)
print(f"{'US bucket':<20} {'n':>7} {'mean P&L':>10} {'median':>10} {'win%':>7} {'std':>8}")
print("-"*70)
for label in labels:
    g = valid[valid["us_bucket"] == label]["p"]
    if len(g) == 0:
        continue
    print(f"{label:<20} {len(g):>7,} {g.mean()*100:>+9.3f}% {g.median()*100:>+9.3f}% "
          f"{(g>0).mean()*100:>6.1f}% {g.std()*100:>7.2f}%")

# --- 5. Split by direction ---
print("\n" + "="*70)
print("U1: SHORT only (our main edge)")
print("="*70)
short = valid[valid["direction"] == "SHORT"]
print(f"{'US bucket':<20} {'n':>7} {'mean P&L':>10} {'median':>10} {'win%':>7}")
print("-"*60)
for label in labels:
    g = short[short["us_bucket"] == label]["p"]
    if len(g) == 0:
        continue
    print(f"{label:<20} {len(g):>7,} {g.mean()*100:>+9.3f}% {g.median()*100:>+9.3f}% "
          f"{(g>0).mean()*100:>6.1f}%")

print("\n" + "="*70)
print("U1: LONG only")
print("="*70)
long_ = valid[valid["direction"] == "LONG"]
print(f"{'US bucket':<20} {'n':>7} {'mean P&L':>10} {'median':>10} {'win%':>7}")
print("-"*60)
for label in labels:
    g = long_[long_["us_bucket"] == label]["p"]
    if len(g) == 0:
        continue
    print(f"{label:<20} {len(g):>7,} {g.mean()*100:>+9.3f}% {g.median()*100:>+9.3f}% "
          f"{(g>0).mean()*100:>6.1f}%")

# --- 6. Statistical test: is US big up -> SHORT P&L significantly higher? ---
print("\n" + "="*70)
print("Statistical test: SHORT P&L when US up >2% vs US flat")
print("="*70)
up = short[short["us_bucket"] == "US大漲(>2%)"]["p"]
flat = short[short["us_bucket"] == "US平(-0.5~0.5%)"]["p"]
if len(up) > 30 and len(flat) > 30:
    t, pval = stats.ttest_ind(up, flat, equal_var=False)
    print(f"  US大漲 n={len(up):,} mean={up.mean()*100:+.3f}%")
    print(f"  US平   n={len(flat):,} mean={flat.mean()*100:+.3f}%")
    print(f"  Welch t-test: t={t:.3f}, p={pval:.4f}")
    print(f"  Difference: {(up.mean()-flat.mean())*100:+.3f}% per trade")
else:
    print("  Insufficient sample for test")

# --- 7. Incremental over pred_q ---
print("\n" + "="*70)
print("Incremental test: does US return add signal after controlling pred_q?")
print("="*70)
# Use only signals that would actually be traded (pred_q >= 0.20)
traded = valid[valid["pred_q"] >= 0.20].copy()
traded["us_bucket"] = pd.cut(traded["us_ret"], bins=bins, labels=labels)
short_traded = traded[traded["direction"] == "SHORT"]
print(f"Traded SHORT (pred_q>=0.20): n={len(short_traded):,}")
print(f"{'US bucket':<20} {'n':>7} {'mean P&L':>10} {'win%':>7}")
print("-"*50)
for label in labels:
    g = short_traded[short_traded["us_bucket"] == label]["p"]
    if len(g) == 0:
        continue
    print(f"{label:<20} {len(g):>7,} {g.mean()*100:>+9.3f}% {(g>0).mean()*100:>6.1f}%")

# --- 8. Recent period only (2022-2026, the target window) ---
print("\n" + "="*70)
print("Recent window only (2022-2026)")
print("="*70)
recent = valid[valid["date"].dt.year >= 2022]
short_recent = recent[recent["direction"] == "SHORT"]
print(f"{'US bucket':<20} {'n':>7} {'mean P&L':>10} {'win%':>7}")
print("-"*50)
for label in labels:
    g = short_recent[short_recent["us_bucket"] == label]["p"]
    if len(g) == 0:
        continue
    print(f"{label:<20} {len(g):>7,} {g.mean()*100:>+9.3f}% {(g>0).mean()*100:>6.1f}%")

# --- 9. Correlation ---
print("\n" + "="*70)
print("Correlation: US return vs trade P&L")
print("="*70)
r_all, p_all = stats.pearsonr(valid["us_ret"], valid["p"])
r_short, p_short = stats.pearsonr(short["us_ret"], short["p"])
print(f"  All:    r={r_all:+.4f}, p={p_all:.2e}, n={len(valid):,}")
print(f"  SHORT:  r={r_short:+.4f}, p={p_short:.2e}, n={len(short):,}")

# Spearman (rank-based, more robust)
r_s, p_s = stats.spearmanr(short["us_ret"], short["p"])
print(f"  SHORT (Spearman): rho={r_s:+.4f}, p={p_s:.2e}")

print("\nDone.")
