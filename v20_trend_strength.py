# -*- coding: utf-8 -*-
r"""U4: Does trend strength reduce gap fade edge?
Uses existing features in signals_v13.pkl as trend proxies.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
from scipy import stats

sig = pd.read_pickle("signals_v13.pkl")
sig["date"] = pd.to_datetime(sig["date"])
short = sig[sig["direction"] == "SHORT"].copy()
print(f"SHORT signals: {len(short):,}")

# --- ret_20 (20-day momentum) ---
print("\n" + "="*70)
print("U4a: 20-day return (ret_20) vs SHORT P&L")
print("="*70)
bins_r = [-np.inf, -0.10, 0, 0.10, 0.30, 0.60, np.inf]
labels_r = ["<-10%", "-10~0%", "0~10%", "10~30%", "30~60%", ">60%"]
short["ret20_bucket"] = pd.cut(short["ret_20"], bins=bins_r, labels=labels_r)
print(f"{'ret_20':<12} {'n':>8} {'mean P&L':>10} {'median':>10} {'win%':>7}")
print("-"*52)
for label in labels_r:
    g = short[short["ret20_bucket"] == label]["p"]
    if len(g) < 10: continue
    print(f"{label:<12} {len(g):>8,} {g.mean()*100:>+9.3f}% {g.median()*100:>+9.3f}% {(g>0).mean()*100:>6.1f}%")

# --- dist_hi60 (distance from 60-day high) ---
print("\n" + "="*70)
print("U4b: Distance from 60-day high (0 = at the high = strongest)")
print("="*70)
bins_d = [-np.inf, -0.30, -0.15, -0.05, -0.01, 0.001]
labels_d = ["<-30%", "-30~-15%", "-15~-5%", "-5~-1%", "at high(>-1%)"]
short["dist_bucket"] = pd.cut(short["dist_hi60"], bins=bins_d, labels=labels_d)
print(f"{'dist_hi60':<16} {'n':>8} {'mean P&L':>10} {'median':>10} {'win%':>7}")
print("-"*56)
for label in labels_d:
    g = short[short["dist_bucket"] == label]["p"]
    if len(g) < 10: continue
    print(f"{label:<16} {len(g):>8,} {g.mean()*100:>+9.3f}% {g.median()*100:>+9.3f}% {(g>0).mean()*100:>6.1f}%")

# --- zt_close_60 (limit-up count) ---
print("\n" + "="*70)
print("U4c: Limit-up closes in 60 days")
print("="*70)
bins_z = [-0.5, 0.5, 2.5, 5.5, 10.5, np.inf]
labels_z = ["0", "1-2", "3-5", "6-10", ">10"]
short["zt_bucket"] = pd.cut(short["zt_close_60"], bins=bins_z, labels=labels_z)
print(f"{'zt_close_60':<12} {'n':>8} {'mean P&L':>10} {'median':>10} {'win%':>7}")
print("-"*52)
for label in labels_z:
    g = short[short["zt_bucket"] == label]["p"]
    if len(g) < 10: continue
    print(f"{label:<12} {len(g):>8,} {g.mean()*100:>+9.3f}% {g.median()*100:>+9.3f}% {(g>0).mean()*100:>6.1f}%")

# --- gapup_60 ---
print("\n" + "="*70)
print("U4d: Gap-up count in 60 days")
print("="*70)
bins_g = [-0.5, 2.5, 5.5, 10.5, 20.5, np.inf]
labels_g = ["0-2", "3-5", "6-10", "11-20", ">20"]
short["gap_bucket"] = pd.cut(short["gapup_60"], bins=bins_g, labels=labels_g)
print(f"{'gapup_60':<10} {'n':>8} {'mean P&L':>10} {'median':>10} {'win%':>7}")
print("-"*50)
for label in labels_g:
    g = short[short["gap_bucket"] == label]["p"]
    if len(g) < 10: continue
    print(f"{label:<10} {len(g):>8,} {g.mean()*100:>+9.3f}% {g.median()*100:>+9.3f}% {(g>0).mean()*100:>6.1f}%")

# --- Combined strong trend filter ---
print("\n" + "="*70)
print("U4 combined: strong = ret_20>30% AND dist_hi60>-5% AND zt_close_60>3")
print("="*70)
strong = (short["ret_20"] > 0.30) & (short["dist_hi60"] > -0.05) & (short["zt_close_60"] > 3)
weak = ~strong
print(f"  Strong: n={strong.sum():,} mean={short[strong]['p'].mean()*100:+.3f}% win={(short[strong]['p']>0).mean()*100:.1f}%")
print(f"  Other:  n={weak.sum():,} mean={short[weak]['p'].mean()*100:+.3f}% win={(short[weak]['p']>0).mean()*100:.1f}%")
t, pval = stats.ttest_ind(short[strong]["p"], short[weak]["p"], equal_var=False)
print(f"  t={t:.3f}, p={pval:.2e}, diff={(short[strong]['p'].mean()-short[weak]['p'].mean())*100:+.3f}%")

# --- Recent window ---
print("\n" + "="*70)
print("Recent (2022-2026)")
print("="*70)
rs = short[short["date"].dt.year >= 2022]
sr = (rs["ret_20"] > 0.30) & (rs["dist_hi60"] > -0.05) & (rs["zt_close_60"] > 3)
wr = ~sr
print(f"  Strong: n={sr.sum():,} mean={rs[sr]['p'].mean()*100:+.3f}% win={(rs[sr]['p']>0).mean()*100:.1f}%")
print(f"  Other:  n={wr.sum():,} mean={rs[wr]['p'].mean()*100:+.3f}% win={(rs[wr]['p']>0).mean()*100:.1f}%")
if sr.sum() > 30:
    t2, p2 = stats.ttest_ind(rs[sr]["p"], rs[wr]["p"], equal_var=False)
    print(f"  t={t2:.3f}, p={p2:.2e}")

# --- Incremental over pred_q ---
print("\n" + "="*70)
print("Incremental (pred_q>=0.20 only)")
print("="*70)
traded = short[short["pred_q"] >= 0.20].copy()
st = (traded["ret_20"] > 0.30) & (traded["dist_hi60"] > -0.05) & (traded["zt_close_60"] > 3)
wt = ~st
print(f"  Strong: n={st.sum():,} mean={traded[st]['p'].mean()*100:+.3f}%")
print(f"  Other:  n={wt.sum():,} mean={traded[wt]['p'].mean()*100:+.3f}%")
if st.sum() > 30:
    t3, p3 = stats.ttest_ind(traded[st]["p"], traded[wt]["p"], equal_var=False)
    print(f"  t={t3:.3f}, p={p3:.2e}")

# --- Correlations ---
print("\n" + "="*70)
print("Spearman correlations with SHORT P&L")
print("="*70)
for col in ["ret_20", "dist_hi60", "zt_close_60", "gapup_60"]:
    r, p = stats.spearmanr(short[col], short["p"])
    print(f"  {col:<15} rho={r:+.4f}, p={p:.2e}")

print("\nDone.")
