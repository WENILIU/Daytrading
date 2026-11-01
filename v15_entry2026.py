# -*- coding: utf-8 -*-
"""The two entry paths, month by month, for the recent years.

The 13-year average is what the target was declared on, but one number per year
cannot tell "the strategy decayed" from "one bad month" - and the two entry paths
differ only by the spread, so the month-by-month gap between them is where that
cost actually lands. It is not constant: the spread is charged on notional, and
2026 trades 16.9 orders/day against a 13-year average of 10.9, so the cost is
~24 pct of capital this year versus ~15 pct on average.

Run: python v15_entry2026.py
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
LIVE = ((-0.006, 0.30), (-0.012, 0.12))
BASE = dict(brake=LIVE, liq=0.10, gap_max=0.04, gap_max_long=0.08, exposure=1.90)
CFG = [("A  08:59 前參與競價（不付價差）", dict(BASE, spread=0.0)),
       ("B  09:01 市價（吃半價差）= live", dict(BASE, spread=T.SPREAD))]
YEARS = (2025, 2026)

out = []
for name, cfg in CFG:
    r = T.run(**cfg)
    y = r["yearly"]
    print("%-34s 13yr %+.1f%%  MDD %+.2f%%  " % (name, np.mean([y[k] / CAP0 * 100 for k in sorted(y)]), r["mdd"])
          + "  ".join("%d %+.1f%%" % (k, y[k] / CAP0 * 100) for k in YEARS)
          + "  筆/日 %.1f" % r["per_day"])
    out.append(r)
print()

mA, mB = out[0]["monthly"], out[1]["monthly"]
for yr in YEARS:
    print("=== %d 逐月（每筆獲利出金、本金釘在 450 萬）===" % yr)
    print("  %-7s %9s %7s %6s | %9s %7s %6s | %8s" %
          ("月", "A 報酬%", "筆", "勝率", "B 報酬%", "筆", "勝率", "價差成本"))
    for m in (mA, mB):
        m[("TOTAL", yr)] = [sum(v[0] for k, v in m.items() if k[0] == yr),
                            sum(v[1] for k, v in m.items() if k[0] == yr),
                            sum(v[2] for k, v in m.items() if k[0] == yr)]
    for mo in sorted(k for k in mA if k[0] == yr and k[1] != yr):
        a = mA.get(mo, [0, 0, 0]); b = mB.get(mo, [0, 0, 0])
        pa = a[0] / CAP0 * 100; pb = b[0] / CAP0 * 100
        print("  %d-%02d  %+8.2f %7d %5.1f%% | %+8.2f %7d %5.1f%% | %7.2f"
              % (mo[0], mo[1], pa, a[1], (a[2] / a[1] * 100) if a[1] else 0,
                 pb, b[1], (b[2] / b[1] * 100) if b[1] else 0, pa - pb))
    a = mA[("TOTAL", yr)]; b = mB[("TOTAL", yr)]
    print("  %-7s %+8.1f %7d %5.1f%% | %+8.1f %7d %5.1f%% | %7.2f"
          % ("全年", a[0] / CAP0 * 100, a[1], a[2] / a[1] * 100,
             b[0] / CAP0 * 100, b[1], b[2] / b[1] * 100,
             (a[0] - b[0]) / CAP0 * 100))
    print("  負月數 A %d / B %d" %
          (sum(1 for k, v in mA.items() if k[0] == yr and k[1] != yr and v[0] < 0),
           sum(1 for k, v in mB.items() if k[0] == yr and k[1] != yr and v[0] < 0)))
    print()
