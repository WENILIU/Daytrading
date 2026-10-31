"""Is there edge concentration? Does the top of the ranking earn more per TWD?

The book cannot exceed 100% exposure with zero margin, so the only way to raise
annual P&L is edge per unit deployed. Concentrating into the top K signals only
helps if rank correlates with edge-per-TWD. Measured here on the raw design list,
net of commission, before any sizing constraint.

Usage: python v13_rankedge.py
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from v13_engine import run_backtest, exit_of_legal, CAP0, COST

CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
_, got, _ = run_backtest(capture=("2014-01-01", "2026-12-31"), capital=CAP0, **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)

g = []
for _, r in D.iterrows():
    pr = float(r["entry"])
    ex, slp, tpp, reason, gross = exit_of_legal(
        r["direction"], pr, float(r["day_high"]), float(r["day_low"]), float(r["day_close"]),
        float(r["lu"]), float(r["ld"]), float(r["tick"]), float(r["tp"]))
    g.append(gross - 2 * COST)
D["net"] = g
D["day_n"] = D.groupby("date")["net"].transform("size")

print("全部訊號 n=%d  淨損益(僅扣手續費) 平均 %+.3f%%  勝率 %.1f%%" % (
    len(D), D["net"].mean() * 100, (D["net"] > 0).mean() * 100))
print()
print("按當日排名分層（rank 1 = 模型最想買的那檔）")
print("%-12s %8s %9s %9s %9s" % ("排名", "筆數", "平均淨PnL%", "勝率%", "最差%"))
for lo, hi in [(1, 1), (2, 2), (3, 3), (4, 5), (6, 10), (11, 20), (21, 99)]:
    m = (D["_rank"] >= lo) & (D["_rank"] <= hi)
    if m.sum() == 0:
        continue
    x = D.loc[m, "net"]
    tag = str(lo) if lo == hi else ("%d-%d" % (lo, hi) if hi < 99 else "21+")
    print("%-12s %8d %9.3f %9.1f %9.2f" % (tag, m.sum(), x.mean() * 100,
          (x > 0).mean() * 100, x.min() * 100))
print()
print("按 score 分層（_weight 高 = 模型給的權重高）")
D["wq"] = pd.qcut(D["_weight"], 5, labels=False, duplicates="drop")
for q in sorted(D["wq"].dropna().unique()):
    x = D.loc[D["wq"] == q, "net"]
    print("  權重第%d層 n=%5d  平均 %+.3f%%  勝率 %.1f%%" % (
        int(q) + 1, len(x), x.mean() * 100, (x > 0).mean() * 100))
print()
print("每日訊號數 vs 該日平均淨PnL（訊號多的日子是不是邊際更高）")
for lo, hi in [(1, 2), (3, 5), (6, 10), (11, 20), (21, 999)]:
    m = (D["day_n"] >= lo) & (D["day_n"] <= hi)
    if m.sum() == 0:
        continue
    x = D.loc[m, "net"]
    tag = "%d-%d" % (lo, hi) if hi < 999 else "21+"
    print("  當日訊號 %-6s n=%5d  平均 %+.3f%%  勝率 %.1f%%" % (
        tag, len(x), x.mean() * 100, (x > 0).mean() * 100))
print()
print("前4名 vs 全部：每元邊際（這是集中度能不能翻倍日均邊際的關鍵）")
for k in (1, 2, 4, 8, 12, 99):
    m = D["_rank"] <= k
    x = D.loc[m, "net"]
    print("  top %-3d n=%5d  平均淨PnL %+.3f%%  勝率 %.1f%%  最差 %.2f%%" % (
        k, len(x), x.mean() * 100, (x > 0).mean() * 100, x.min() * 100))
