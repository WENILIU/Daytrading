# -*- coding: utf-8 -*-
r"""The last cells needed before any live config is touched.

v19_ordercap.py found the lever: order_cap 30 -> 20 moves the position MDD from
-6.59 to -4.80 pct for 1.7 pp of return, because the worst day in this book is one
day with ~30 one-direction trades and a count cap drops the LOWEST ranked ones. It
binds on about one morning in ten and is nearly free everywhere else.

Two things that sweep did not settle:
  - live runs A (stop armed). A at gap 0.030 / cap 20 is +46.4 / -4.24. Is A at
    0.035 or 0.040 with cap 20 better? Without those two cells the "tighten
    gap_max_short to 0.03" recommendation is taken from the cap=30 rows, which the
    count cap just proved is a different book.
  - does the frontier keep going past 0.040 once the count is capped? At cap 30 it
    turned over at 0.040, but that turnover was measured on the un-capped tail.
  - is the widened brake (50/25 at -0.008/-0.016) doing the work, or the count cap?
    G (brake 45/22) at cap 20 separates them.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00, order_cap=20,
            cost_mode="measured", gap_max_long=0.08, spread=0.00105)
GP = dict(nosl=True, brake=((-0.008, .50), (-0.016, .25)))
G45 = dict(nosl=True, brake=((-0.006, .45), (-0.012, .22)))
A_ = dict(nosl=False, brake=((-0.006, .50), (-0.012, .25)))
CASES = [("A  gap<=0.035 oc20", dict(A_, gap_max=0.035)),
         ("A  gap<=0.040 oc20", dict(A_, gap_max=0.040)),
         ("G+ gap<=0.045 oc20", dict(GP, gap_max=0.045)),
         ("G+ gap<=0.050 oc20", dict(GP, gap_max=0.050)),
         ("G45 gap<=0.040 oc20", dict(G45, gap_max=0.040)),
         ("G45 gap<=0.030 oc20", dict(G45, gap_max=0.030))]

HDR = "%-22s %+6s %+8s %+8s %7s %7s %7s %6s" % (
    "配置", "13yr", "2014-21", "2022-26", "MDD", "最差年", "鎖價率", "筆/日")
rows = []
print(HDR, flush=True)
for tag, cfg in CASES:
    y = T.run(**dict(base, **cfg))
    yr = y["yearly"]; ks = sorted(yr)
    v = [yr[k] / CAP * 100 for k in ks]

    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    a, o, r, m, w = (sum(v) / len(v), avg(2014, 2021), avg(2022, 2026), y["mdd"], min(v))
    pinrate = y["n_pin_dir"]["SHORT"] / max(y["n"], 1) * 100
    flag = "  <- MDD 內" if m >= -5.0 else ""
    print("%-22s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %6.1f%% %6.1f%s"
          % (tag, a, o, r, m, w, pinrate, y["per_day"], flag), flush=True)
    print("      逐年%：", " ".join("%d %+.0f" % (k, x) for k, x in zip(ks, v)), flush=True)
    rows.append(dict(case=tag, all=a, old=o, recent=r, mdd=m, worst=w,
                     pinrate=pinrate, per_day=y["per_day"], n=y["n"]))
pd.DataFrame(rows).to_csv("_ordercap2.csv", index=False)
print("saved _ordercap2.csv", flush=True)
