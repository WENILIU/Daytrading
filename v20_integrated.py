import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np

merged = pd.read_pickle("v20_features_cache.pkl")
merged["p_0901"] = merged["p"] + merged["bar1_body"]
print("Total signals: %d" % len(merged))

def bt(df, pnl_col, pos_frac, cap=20, label=""):
    if len(df) == 0: return None
    df = df.sort_values(["date","pred_q"], ascending=[True,False]).groupby("date").head(cap)
    daily = df.groupby("date").apply(lambda g: (pos_frac * g[pnl_col]).sum(), include_groups=False)
    cum = (1+daily).cumprod()
    n_years = len(daily)/240
    cagr = (cum.iloc[-1]**(1/n_years)-1)*100 if cum.iloc[-1] > 0 else -100
    mdd = ((cum/cum.cummax())-1).min()*100
    yearly = df.copy(); yearly["year"] = yearly["date"].dt.year
    yr_rets = yearly.groupby("year").apply(lambda g: (pos_frac * g[pnl_col]).sum()*100, include_groups=False)
    yr_dd = {}
    for yr, gg in yearly.groupby("year"):
        d = gg.groupby("date").apply(lambda x: (pos_frac * x[pnl_col]).sum(), include_groups=False)
        c = (1+d).cumprod()
        yr_dd[yr] = ((c/c.cummax())-1).min()*100
    return dict(label=label, n=len(df), per_day=len(df)/len(daily), CAGR=cagr, MDD=mdd,
                yearly=yr_rets.to_dict(), yr_dd=yr_dd, mean_p=df[pnl_col].mean()*100)

print("\n" + "="*100)
print("INTEGRATED TESTS: model (pred_q) x 1-min filter, pos=5%, cap=20/day")
print("="*100)
print()
print("%-50s %6s %6s %8s %7s %8s" % ("Strategy","n","per_day","mean_p","CAGR","MDD"))
print("-"*90)

tests = []

# v13 baseline (current: pred_q >= 0.20 only)
tests.append(bt(merged[merged["pred_q"]>=0.20], "p", 0.05, 20, "v13 baseline: pred_q>=0.20 (09:00)"))

# New S3 filter alone
tests.append(bt(merged[merged["price_dir"] < -0.005], "p_0901", 0.05, 20, "S3 alone: price down >0.5% (09:01)"))

# Combined: v13 model + 1-min filter
tests.append(bt(merged[(merged["pred_q"]>=0.20) & (merged["price_dir"]<-0.005)], "p_0901", 0.05, 20, "v13 + S3 filter (09:01)"))

# Stricter combined
tests.append(bt(merged[(merged["pred_q"]>=0.40) & (merged["price_dir"]<-0.005)], "p_0901", 0.05, 20, "v13 (q>=0.40) + S3 (09:01)"))
tests.append(bt(merged[(merged["pred_q"]>=0.60) & (merged["price_dir"]<-0.005)], "p_0901", 0.05, 20, "v13 (q>=0.60) + S3 (09:01)"))
tests.append(bt(merged[(merged["pred_q"]>=0.80) & (merged["price_dir"]<-0.005)], "p_0901", 0.05, 20, "v13 (q>=0.80) + S3 (09:01)"))

# Volume-price divergence + v13 model
tests.append(bt(merged[(merged["pred_q"]>=0.20) & (merged["vol_vs_hist"]>2.0) & (merged["price_dir"]<-0.005)], "p_0901", 0.05, 20, "v13 + volprice_diverge (09:01)"))

for r in tests:
    if r is None: continue
    print("%-50s %6d %6.1f %+7.3f%% %+7.1f%% %+7.2f%%" % (
        r["label"], r["n"], r["per_day"], r["mean_p"], r["CAGR"], r["MDD"]))

# Best candidate (v13+S3): scale position
print("\n" + "="*100)
print("POSITION SCALING for 'v13 + S3' at different sizes")
print("="*100)
best = merged[(merged["pred_q"]>=0.20) & (merged["price_dir"]<-0.005)]
for pf in [0.03, 0.05, 0.08, 0.10, 0.15, 0.20]:
    r = bt(best, "p_0901", pf, 20, "")
    cal = abs(r["CAGR"]/r["MDD"]) if r["MDD"] < -0.1 else 0
    print("  pos=%4.0f%%: CAGR=%+7.1f%% MDD=%+6.2f%% calmar=%5.1f" % (pf*100, r["CAGR"], r["MDD"], cal))

# Best candidate with v13+S3 at pos=5%, year by year
print("\n" + "="*100)
print("YEAR BY YEAR: v13 (q>=0.20) + S3 @ pos=5%")
print("="*100)
r = bt(best, "p_0901", 0.05, 20, "")
for yr in sorted(r["yearly"]):
    print("  %d: ret=%+6.1f%% MDD=%+6.2f%%" % (yr, r["yearly"][yr], r["yr_dd"][yr]))

# Also test: does this work in the EARLIER half? (out-of-sample split)
print("\n" + "="*100)
print("OUT-OF-SAMPLE SPLIT: 2023-05 to 2024-12 (train) vs 2025-01 to 2026-10 (test)")
print("="*100)
train = best[best["date"] < "2025-01-01"]
test = best[best["date"] >= "2025-01-01"]
r_tr = bt(train, "p_0901", 0.05, 20, "")
r_te = bt(test, "p_0901", 0.05, 20, "")
print("  Train (2023-05 to 2024-12): n=%d CAGR=%+.1f%% MDD=%+.2f%%" % (r_tr["n"], r_tr["CAGR"], r_tr["MDD"]))
print("  Test  (2025-01 to 2026-10): n=%d CAGR=%+.1f%% MDD=%+.2f%%" % (r_te["n"], r_te["CAGR"], r_te["MDD"]))

# Also: does threshold -0.5% hold in BOTH halves?
print("\n" + "="*100)
print("Threshold robustness in both halves (pos=5%, v13 q>=0.20)")
print("="*100)
for th in [-0.003, -0.005, -0.008, -0.01]:
    t1 = merged[(merged["pred_q"]>=0.20) & (merged["price_dir"]<th) & (merged["date"]<"2025-01-01")]
    t2 = merged[(merged["pred_q"]>=0.20) & (merged["price_dir"]<th) & (merged["date"]>="2025-01-01")]
    r1 = bt(t1, "p_0901", 0.05, 20, "")
    r2 = bt(t2, "p_0901", 0.05, 20, "")
    print("  th=%+.1f%%: train CAGR=%+7.1f%% MDD=%+6.2f%% | test CAGR=%+7.1f%% MDD=%+6.2f%%" % (
        th*100, r1["CAGR"], r1["MDD"], r2["CAGR"], r2["MDD"]))
