import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np

merged = pd.read_pickle("v20_features_cache.pkl")
print("Signals: %d" % len(merged))

# Realistic implementation:
# All signals enter at 09:00 (use p).
# If first bar is RED at 09:01, exit immediately. Cost = bar1_body (price went against us by that much).
# If first bar is BLACK, keep normal p.
# So new_p = p for black, bar1_body for red (a small loss = the red K body itself)
# Conservative: add half spread + slippage to the early exit cost.

merged["new_p"] = np.where(merged["bar1_black"], merged["p"], merged["bar1_body"] - 0.001)  # 0.1% for spread/slippage on early exit
# Note: bar1_body is negative for red K? No wait: bar1_body < 0 means BLACK (close < open). So if NOT black (red), bar1_body >= 0.
# For shorts, red K means price went UP by bar1_body -> our loss = -bar1_body (price went against us)
# Wait: bar1_body = (close-open)/open. For red K (close > open), body > 0. For SHORT, this is a loss.
# So early exit cost for SHORT = -bar1_body (positive number when red)
# Correction:
merged["new_p"] = np.where(merged["bar1_black"], merged["p"], -merged["bar1_body"] - 0.001)

# Wait, this is wrong sign. bar1_body > 0 means RED (close > open). For short, that's a loss of bar1_body.
# So new_p = -bar1_body - cost when red. Since bar1_body > 0 for red, new_p < 0 (loss).
# Let me check: 
red_mask = ~merged["bar1_black"]
print("Red K: mean bar1_body = %+.3f%% (price rose this much against us)" % (merged[red_mask]["bar1_body"].mean()*100))
print("Black K: mean bar1_body = %+.3f%% (price fell this much)" % (merged[~red_mask]["bar1_body"].mean()*100))
print("Red K original p (let run): mean = %+.3f%%" % (merged[red_mask]["p"].mean()*100))

def backtest_pnl(df, pos_frac, cap=20):
    df = df.sort_values(["date","pred_q"], ascending=[True,False])
    df = df.groupby("date").head(cap)
    daily = df.groupby("date").apply(lambda g: (pos_frac * g["new_p"] if "new_p" in g.columns else pos_frac * g["p"]).sum(), include_groups=False)
    cum = (1+daily).cumprod()
    n_days = len(daily)
    n_years = n_days / 240
    cagr = (cum.iloc[-1]**(1/n_years)-1)*100 if cum.iloc[-1] > 0 else -100
    mdd = ((cum/cum.cummax())-1).min()*100
    return cagr, mdd, daily.mean()*100

# Test: full strategy with realistic red K quick stop
print("\n" + "="*80)
print("REALISTIC: enter 09:00, red K -> exit 09:01 (small loss)")
print("="*80)
print("%-5s %10s %8s %10s" % ("pos","CAGR","MDD","daily mean"))
for pf in [0.02, 0.03, 0.05, 0.08, 0.10, 0.15]:
    cagr, mdd, dm = backtest_pnl(merged, pf)
    print("  %4.0f%% %+9.1f%% %+7.2f%% %+8.3f%%" % (pf*100, cagr, mdd, dm))

# Compare to all signals (no filter, just current p)
print("\n" + "="*80)
print("BASELINE: all signals at 09:00 (current)")
print("="*80)
def backtest_baseline(df, pos_frac, cap=20):
    df = df.sort_values(["date","pred_q"], ascending=[True,False])
    df = df.groupby("date").head(cap)
    daily = df.groupby("date").apply(lambda g: (pos_frac * g["p"]).sum(), include_groups=False)
    cum = (1+daily).cumprod()
    n_days = len(daily)
    n_years = n_days / 240
    cagr = (cum.iloc[-1]**(1/n_years)-1)*100 if cum.iloc[-1] > 0 else -100
    mdd = ((cum/cum.cummax())-1).min()*100
    return cagr, mdd
print("%-5s %10s %8s" % ("pos","CAGR","MDD"))
for pf in [0.02, 0.03, 0.05, 0.08, 0.10, 0.15]:
    cagr, mdd = backtest_baseline(merged, pf)
    print("  %4.0f%% %+9.1f%% %+7.2f%%" % (pf*100, cagr, mdd))

# What does the red K quick stop actually save?
print("\n" + "="*80)
print("Cost comparison for red K signals:")
print("="*80)
print("  If we let them run: mean = %+.3f%%" % (merged[red_mask]["p"].mean()*100))
print("  If we exit at 09:01: mean = %+.3f%%" % (merged[red_mask]["new_p"].mean()*100))
print("  Savings per red K trade: %+.3f%%" % ((merged[red_mask]["new_p"].mean() - merged[red_mask]["p"].mean())*100))
print("  Red K count: %d (39%% of all)" % red_mask.sum())
print("  Total savings: %+.3f%%" % ((merged[red_mask]["new_p"] - merged[red_mask]["p"]).sum()*100))
