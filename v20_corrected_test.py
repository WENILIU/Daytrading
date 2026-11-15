import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np

merged = pd.read_pickle("v20_features_cache.pkl")
print("Signals: %d" % len(merged))

# CORRECT adjustment: enter at 09:01 (just after bar 1 closes)
# Bar 1 = 09:00 to 09:01. Its close = bar1_close. We enter at bar1_close.
# Original p was measured from bar1_open.
# For shorts: new_p = p + bar1_body (where bar1_body is close/open - 1)
# Black K: bar1_body < 0 -> new_p is lower (we entered at a worse price)
# Red K: bar1_body > 0 -> new_p is HIGHER (we entered at a better price for short!)

merged["p_0901"] = merged["p"] + merged["bar1_body"]
print("Baseline (09:00):  mean p = %+.3f%%" % (merged["p"].mean()*100))
print("Adjusted (09:01):  mean p = %+.3f%%" % (merged["p_0901"].mean()*100))
print("Adjustment: %+.3f%% (= mean bar1_body)" % ((merged["p_0901"].mean()-merged["p"].mean())*100))

# Now apply filter at 09:01 with the CORRECT adjusted P&L
print("\n" + "="*80)
print("Filter: black K only, enter at 09:01 (p + bar1_body adjustment)")
print("="*80)

def backtest(df, pnl_col, pos_frac, cap=20):
    df = df.sort_values(["date","pred_q"], ascending=[True,False])
    df = df.groupby("date").head(cap)
    daily = df.groupby("date").apply(lambda g: (pos_frac * g[pnl_col]).sum(), include_groups=False)
    cum = (1+daily).cumprod()
    n_days = len(daily)
    n_years = n_days/240
    cagr = (cum.iloc[-1]**(1/n_years)-1)*100 if cum.iloc[-1] > 0 else -100
    mdd = ((cum/cum.cummax())-1).min()*100
    return cagr, mdd

print("%-30s %8s %8s %8s" % ("Strategy","pos","CAGR","MDD"))
print("-"*65)

# Black K filter with 09:01 entry (corrected)
bk = merged[merged["bar1_black"]]
for pf in [0.05, 0.08, 0.10, 0.15, 0.20]:
    cagr, mdd = backtest(bk, "p_0901", pf)
    print("  Black K @09:01 (n=%d)        %5.0f%% %+7.1f%% %+6.2f%%" % (len(bk), pf*100, cagr, mdd))

# Compare: Black K at 09:00 (look-ahead, for reference)
print()
for pf in [0.05, 0.08, 0.10]:
    cagr, mdd = backtest(bk, "p", pf)
    print("  [Look-ahead] BlackK @09:00     %5.0f%% %+7.1f%% %+6.2f%%" % (pf*100, cagr, mdd))

# Compare: All signals (baseline)
print()
for pf in [0.05, 0.08, 0.10]:
    cagr, mdd = backtest(merged, "p", pf)
    print("  Baseline all @09:00           %5.0f%% %+7.1f%% %+6.2f%%" % (pf*100, cagr, mdd))

# Compare: All signals at 09:01 (just delayed entry, no filter)
print()
for pf in [0.05, 0.08, 0.10]:
    cagr, mdd = backtest(merged, "p_0901", pf)
    print("  All @09:01 (delayed, no filt) %5.0f%% %+7.1f%% %+6.2f%%" % (pf*100, cagr, mdd))

# S4: Black K + price down >0.5%, enter 09:01
print("\n" + "="*80)
print("S4: BlackK + down >0.5% @ 09:01 (corrected)")
print("="*80)
s4 = merged[merged["bar1_black"] & (merged["price_dir"] < -0.005)]
print("n=%d" % len(s4))
for pf in [0.05, 0.10, 0.15, 0.20, 0.25]:
    cagr, mdd = backtest(s4, "p_0901", pf)
    print("  pos=%5.0f%%: CAGR=%+7.1f%% MDD=%+6.2f%% calmar=%5.1f" % (pf*100, cagr, mdd, abs(cagr/mdd) if mdd<-0.1 else 0))

# S3: price down >0.5% only (most aggressive, doesn't care about black K)
print("\n" + "="*80)
print("S3: Price down >0.5% @ 09:01")
print("="*80)
s3 = merged[merged["price_dir"] < -0.005]
print("n=%d" % len(s3))
for pf in [0.05, 0.10, 0.15, 0.20, 0.25]:
    cagr, mdd = backtest(s3, "p_0901", pf)
    print("  pos=%5.0f%%: CAGR=%+7.1f%% MDD=%+6.2f%% calmar=%5.1f" % (pf*100, cagr, mdd, abs(cagr/mdd) if mdd<-0.1 else 0))

# S5: Volume-price divergence @ 09:01
print("\n" + "="*80)
print("S5: VolPriceDiverge (>2x + down) @ 09:01")
print("="*80)
s5 = merged[(merged["vol_vs_hist"] > 2.0) & (merged["price_dir"] < -0.005)]
print("n=%d" % len(s5))
for pf in [0.05, 0.10, 0.15, 0.20, 0.25]:
    cagr, mdd = backtest(s5, "p_0901", pf)
    print("  pos=%5.0f%%: CAGR=%+7.1f%% MDD=%+6.2f%% calmar=%5.1f" % (pf*100, cagr, mdd, abs(cagr/mdd) if mdd<-0.1 else 0))

# Best combo: black K + vol>2x + price down >1%
print("\n" + "="*80)
print("S8: BlackK + vol>2x + down>1% @ 09:01 (strongest filter)")
print("="*80)
s8 = merged[merged["bar1_black"] & (merged["vol_vs_hist"] > 2.0) & (merged["price_dir"] < -0.01)]
print("n=%d" % len(s8))
for pf in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]:
    cagr, mdd = backtest(s8, "p_0901", pf)
    print("  pos=%5.0f%%: CAGR=%+7.1f%% MDD=%+6.2f%% calmar=%5.1f" % (pf*100, cagr, mdd, abs(cagr/mdd) if mdd<-0.1 else 0))
