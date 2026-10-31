"""Turn the open-liquidity curve into a capacity number instead of a guess.

Two separate capacity limits, and the second one is the one people miss:

1. Impact. notional = weight * capital, and the model's weights are capital-
   independent fractions, so participation scales LINEARLY with capital. Given the
   measured participation at 4.5M, the capital that keeps X% of orders under a
   participation cap is just X / part_q * 4.5M. No model needed.

2. The gate itself. min_turnover_factor is written as dv1 >= factor * capital, so
   raising capital raises the liquidity floor and shrinks the signal pool. The same
   factor that is loose at 4.5M silently deletes most of the book at 20M.

Both are computed from the order-level CSVs v13_open_liquidity.py already wrote.
The 09:00 column is the conservative denominator (it still includes the auction, so
even this is optimistic); 09:01 is the optimistic one.

Usage: python v13_capacity.py
"""
import os
import numpy as np, pandas as pd

CAP0 = 4_500_000
OUT = r"D:\AI專案\StockAgent\DayTrading"
FILES = {"f=5.0 現行": "open_liquidity_5_0.csv", "f=2.0": "open_liquidity_2_0.csv",
         "無門檻": "open_liquidity_off.csv"}
DENOM = {"09:00（保守）": "09:00", "09:01（樂觀）": "09:01"}
TARGETS = [0.10, 0.20, 0.30]
QS = [50, 90, 99]  # np.percentile takes 0-100, not 0-1

for label, fn in FILES.items():
    R = pd.read_csv(os.path.join(OUT, fn))
    R["code"] = R["code"].astype(str)
    print("=== %s（n=%d）===" % (label, len(R)))
    for dname, dcol in DENOM.items():
        ok = R[R[dcol] > 0].copy()
        p = ok["notional"] / (ok["day_value"] * ok[dcol])
        print("  分母 %s  n=%d" % (dname, len(ok)))
        print("    450萬時的參與率      p50 %6.2f%%  p90 %6.2f%%  p99 %6.2f%%" %
              tuple(np.percentile(p * 100, q) for q in QS))
        print("    資金上限（不超過該參與率的訂單占 q）")
        for X in TARGETS:
            caps = [X / qv * CAP0 / 1e6 if qv > 0 else np.inf for qv in np.percentile(p, QS)]
            print("      上限 %3.0f%%   p50 %7.1fM   p90 %7.1fM   p99 %7.1fM" %
                  (X * 100, *caps))
    print()
    print("  第二條限制：factor 門檻本身會隨資金抬高（dv1 >= factor*capital）")
    dv = R["dv1"].dropna()
    print("    這批訂單的 T-1 成交額：p10 %s  p50 %s  p90 %s" %
          tuple("{:,.0f}".format(v) for v in np.percentile(dv, [10, 50, 90])))
    for f in (5.0, 2.0, 1.0):
        line = []
        for cap in (4_500_000, 10_000_000, 20_000_000, 50_000_000):
            line.append("%.0f%%" % ((dv >= f * cap).mean() * 100))
        print("      factor %.1f  資金存活率  450萬 %s  1000萬 %s  2000萬 %s  5000萬 %s" %
              (f, *line))
    print()
