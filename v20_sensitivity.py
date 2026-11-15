import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np

merged = pd.read_pickle("v20_features_cache.pkl")
merged["p_0901"] = merged["p"] + merged["bar1_body"]

def backtest(df, pnl_col, pos_frac, cap=20):
    if len(df) == 0: return None
    df = df.sort_values(["date","pred_q"], ascending=[True,False])
    df = df.groupby("date").head(cap)
    daily = df.groupby("date").apply(lambda g: (pos_frac * g[pnl_col]).sum(), include_groups=False)
    cum = (1+daily).cumprod()
    n_years = len(daily)/240
    cagr = (cum.iloc[-1]**(1/n_years)-1)*100 if cum.iloc[-1] > 0 else -100
    mdd = ((cum/cum.cummax())-1).min()*100
    return cagr, mdd, len(df), len(daily)

# Threshold sensitivity: S3 (price down >X%) @ 09:01, pos=5%
print("="*80)
print("THRESHOLD SENSITIVITY: S3 'price down >X%' at 09:01, pos=5%")
print("="*80)
print("%-12s %6s %6s %8s %8s" % ("threshold","n","days","CAGR","MDD"))
for th in [-0.003, -0.004, -0.005, -0.006, -0.007, -0.008, -0.01, -0.015, -0.02]:
    s = merged[merged["price_dir"] < th]
    r = backtest(s, "p_0901", 0.05)
    if r is None: continue
    cagr, mdd, n, days = r
    print("  %+.2f%%     %5d %5d %+7.1f%% %+7.2f%%" % (th*100, n, days, cagr, mdd))

# Year-by-year breakdown of S3 (-0.5%) to check stability
print("\n" + "="*80)
print("S3 (-0.5%) year-by-year @ pos=5%")
print("="*80)
s3 = merged[merged["price_dir"] < -0.005].copy()
s3["year"] = s3["date"].dt.year
for yr in sorted(s3["year"].unique()):
    df_yr = s3[s3["year"] == yr].sort_values(["date","pred_q"], ascending=[True,False]).groupby("date").head(20)
    daily = df_yr.groupby("date").apply(lambda g: (0.05 * g["p_0901"]).sum(), include_groups=False)
    n_days = len(daily)
    if n_days < 30: continue
    cum = (1+daily).cumprod()
    cagr = (cum.iloc[-1]-1)*100
    mdd = ((cum/cum.cummax())-1).min()*100
    print("  %d: n=%4d days=%3d  ret=%+6.1f%% MDD=%+6.2f%%" % (yr, len(df_yr), n_days, cagr, mdd))

# What fraction of days have at least one trade? (liquidity concern)
print("\n" + "="*80)
print("Trading days coverage for S3:")
print("="*80)
total_days = merged["date"].nunique()
trade_days = s3.groupby("date").head(20)["date"].nunique()
print("  Total session days in window: %d" % total_days)
print("  Days with at least 1 S3 trade: %d (%.0f%%)" % (trade_days, trade_days/total_days*100))

# Daily trade count distribution
print("\nS3 daily trade count distribution:")
counts = s3.groupby("date").head(20).groupby("date").size()
print("  median=%d p25=%d p75=%d max=%d mean=%.1f" % (counts.median(), counts.quantile(0.25), counts.quantile(0.75), counts.max(), counts.mean()))
