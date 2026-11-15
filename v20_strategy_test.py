# -*- coding: utf-8 -*-
r"""Strategy-level backtest: how does the exhaustion filter change CAGR/MDD?

Tests the 42k signal window (2023-05 to 2026-10) with daily-level simulation:
- Current strategy (all signals at 09:00)
- Black K filter (only take first-bar-black signals)
- Volume-price divergence filter
- Black K + adjusted entry (09:02 entry)
- Various position sizing to find path to CAGR 200%

Uses the same P&L per trade from v13 backtest, but adds the 1-min filter.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os
from scipy import stats

DATA_PATH = r"D:\Codex\2026-11-14\new-chat-2\outputs\capital_stock_data\data\fugle_1m"

# Load the merged results from v3 (re-run the fast part)
sig = pd.read_pickle("signals_v13.pkl")
sig["date"] = pd.to_datetime(sig["date"])
short = sig[(sig["direction"] == "SHORT") & (sig["date"] >= "2023-05-23")].copy()
short["stock_str"] = short["stock"].astype(str)

available = set(f.replace(".parquet","") for f in os.listdir(DATA_PATH) if f.endswith(".parquet"))
short = short[short["stock_str"].isin(available)].copy()

# Load features (same as v3 but we'll cache)
CACHE = "v20_features_cache.pkl"
if os.path.exists(CACHE):
    merged = pd.read_pickle(CACHE)
    print("Loaded cached features: %d rows" % len(merged))
else:
    print("Computing features from parquet...")
    stocks = short["stock_str"].unique()
    all_features = []
    for i, stock in enumerate(stocks):
        if i % 300 == 0: print("  %d/%d..." % (i, len(stocks)))
        fp = os.path.join(DATA_PATH, stock + ".parquet")
        try: d = pd.read_parquet(fp)
        except: continue
        d["time"] = pd.to_datetime(d["time"])
        d["date"] = d["time"].dt.date
        d["hhmm"] = d["time"].dt.strftime("%H:%M")
        ob = d[d["hhmm"].isin(["09:00","09:01","09:02"])].sort_values("time")
        if len(ob) == 0: continue
        bar1 = ob.groupby("date").first().rename(columns={"open":"bar1_open","close":"bar1_close"})
        bar_last = ob.groupby("date").last().rename(columns={"close":"close_0902"})
        vol_sum = ob.groupby("date")["volume"].sum().rename("vol_3min")
        feat = bar1[["bar1_open","bar1_close"]].join(bar_last[["close_0902"]]).join(vol_sum).reset_index()
        feat["date"] = pd.to_datetime(feat["date"])
        feat["bar1_body"] = np.where(feat["bar1_open"]>0, (feat["bar1_close"]-feat["bar1_open"])/feat["bar1_open"], 0)
        feat["bar1_black"] = feat["bar1_body"] < 0
        feat["price_dir"] = np.where(feat["bar1_open"]>0, (feat["close_0902"]-feat["bar1_open"])/feat["bar1_open"], 0)
        med = feat["vol_3min"].median()
        feat["vol_vs_hist"] = feat["vol_3min"] / med if med > 0 else 1.0
        feat["stock_str"] = stock
        all_features.append(feat[["date","stock_str","bar1_black","bar1_body","price_dir","vol_vs_hist"]])
    feat_all = pd.concat(all_features, ignore_index=True)
    sig_use = short[["date","stock_str","p","pred_q","adj_gap","day_close","entry","prev_turnover"]].copy()
    merged = sig_use.merge(feat_all, on=["date","stock_str"], how="inner")
    merged.to_pickle(CACHE)
    print("Cached: %d rows" % len(merged))

print("Signals: %d, Date: %s to %s" % (len(merged), merged["date"].min().date(), merged["date"].max().date()))

# === Daily backtest simulation ===
# For each day: sum of P&L * position_size for all signals that day
# Position size: 1/N of budget (simplified, no compounding for now)
# Then compute daily returns, CAGR, MDD

def backtest(strategy_df, label, cap_per_day=20, pos_frac=0.05):
    """Simulate daily P&L with position sizing.
    strategy_df must have: date, p (per-trade P&L as fraction of notional)
    pos_frac: fraction of net value per trade
    cap_per_day: max trades per day
    """
    df = strategy_df.sort_values(["date","pred_q"], ascending=[True,False])
    # Apply daily cap
    df = df.groupby("date").head(cap_per_day).copy()
    # Daily return = sum(pos_frac * p) for that day
    daily = df.groupby("date").apply(lambda g: (pos_frac * g["p"]).sum(), include_groups=False)
    daily = daily.rename("ret")
    # Cumulative
    cum = (1 + daily).cumprod()
    # Metrics
    n_days = len(daily)
    n_years = n_days / 240
    total = cum.iloc[-1]
    cagr = (total ** (1/n_years) - 1) * 100 if n_years > 0 and total > 0 else -100
    dd = (cum / cum.cummax() - 1)
    mdd = dd.min() * 100
    trades_per_day = len(df) / n_days
    win = (df["p"] > 0).mean() * 100
    mean_p = df["p"].mean() * 100
    return dict(label=label, n_trades=len(df), per_day=trades_per_day, mean_p=mean_p,
                win=win, cagr=cagr, mdd=mdd, total=total*100-100, n_days=n_days)

# === Define strategies ===
results = []

# S0: All signals (baseline)
results.append(backtest(merged, "S0: All (baseline)"))

# S1: Black K only
s1 = merged[merged["bar1_black"]].copy()
results.append(backtest(s1, "S1: Black K only"))

# S2: Black K + pred_q >= 0.20 (model confirms)
s2 = merged[merged["bar1_black"] & (merged["pred_q"] >= 0.20)].copy()
results.append(backtest(s2, "S2: BlackK + model"))

# S3: Price down at 09:02 (>0.5%)
s3 = merged[merged["price_dir"] < -0.005].copy()
results.append(backtest(s3, "S3: Price down >0.5%"))

# S4: Black K + price down
s4 = merged[merged["bar1_black"] & (merged["price_dir"] < -0.005)].copy()
results.append(backtest(s4, "S4: BlackK + down"))

# S5: Volume-price divergence (>2x vol + price down)
s5 = merged[(merged["vol_vs_hist"] > 2.0) & (merged["price_dir"] < -0.005)].copy()
results.append(backtest(s5, "S5: VolPriceDiverge"))

# S6: Black K + volume >1x + model
s6 = merged[merged["bar1_black"] & (merged["vol_vs_hist"] > 1.0) & (merged["pred_q"] >= 0.20)].copy()
results.append(backtest(s6, "S6: BlackK+Vol+Model"))

# S7: Aggressive - black K + vol>2x + pred_q>=0.5
s7 = merged[merged["bar1_black"] & (merged["vol_vs_hist"] > 2.0) & (merged["pred_q"] >= 0.5)].copy()
results.append(backtest(s7, "S7: Aggressive filter"))

# === Print results ===
print("\n" + "="*100)
print("DAILY BACKTEST (2023-05 to 2026-10, pos=5%%/trade, cap=20/day)")
print("="*100)
print("%-28s %6s %6s %8s %6s %8s %7s" % ("Strategy","n","per_day","mean_p","win%","CAGR","MDD"))
print("-"*80)
for r in results:
    print("%-28s %6d %6.1f %+7.3f%% %5.1f%% %+7.1f%% %+6.1f%%" % (
        r["label"], r["n_trades"], r["per_day"], r["mean_p"], r["win"], r["cagr"], r["mdd"]))

# === Now try larger position sizes for the best filters ===
print("\n" + "="*100)
print("POSITION SCALING: S1 (Black K) at different sizes")
print("="*100)
for pf in [0.05, 0.08, 0.10, 0.15, 0.20, 0.25]:
    r = backtest(s1, "pos=%.0f%%" % (pf*100), pos_frac=pf)
    print("  pos=%5.0f%%: CAGR=%+7.1f%% MDD=%+6.1f%% calmar=%5.1f" % (
        pf*100, r["cagr"], r["mdd"], abs(r["cagr"]/r["mdd"]) if r["mdd"] < -0.1 else 0))

print("\nPOSITION SCALING: S4 (BlackK + down) at different sizes")
for pf in [0.05, 0.08, 0.10, 0.15, 0.20, 0.25]:
    r = backtest(s4, "pos=%.0f%%" % (pf*100), pos_frac=pf)
    print("  pos=%5.0f%%: CAGR=%+7.1f%% MDD=%+6.1f%% calmar=%5.1f" % (
        pf*100, r["cagr"], r["mdd"], abs(r["cagr"]/r["mdd"]) if r["mdd"] < -0.1 else 0))

print("\nPOSITION SCALING: S2 (BlackK+Model) at different sizes")
for pf in [0.05, 0.08, 0.10, 0.15, 0.20, 0.25]:
    r = backtest(s2, "pos=%.0f%%" % (pf*100), pos_frac=pf)
    print("  pos=%5.0f%%: CAGR=%+7.1f%% MDD=%+6.1f%% calmar=%5.1f" % (
        pf*100, r["cagr"], r["mdd"], abs(r["cagr"]/r["mdd"]) if r["mdd"] < -0.1 else 0))

# === Entry at 09:02 (adjusted P&L) vs 09:00 ===
print("\n" + "="*100)
print("Entry timing: 09:00 vs 09:02 adjusted")
print("="*100)
s1_adj = s1.copy()
s1_adj["p"] = s1_adj["p"] + s1_adj["price_dir"]  # adjusted for 09:02 entry
r_0900 = backtest(s1, "S1 at 09:00")
r_0902 = backtest(s1_adj, "S1 at 09:02")
print("  S1 (BlackK) 09:00: CAGR=%+.1f%% MDD=%+.1f%%" % (r_0900["cagr"], r_0900["mdd"]))
print("  S1 (BlackK) 09:02: CAGR=%+.1f%% MDD=%+.1f%%" % (r_0902["cagr"], r_0902["mdd"]))

print("\nDone.")
