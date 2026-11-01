# -*- coding: utf-8 -*-
"""The yearly table for the candidate shipped book: same 450 萬 cap, same entry,
brake shrink factors 50/25 instead of 30/12.

Chosen because it improves BOTH windows - 2014-2021 (never used to pick anything)
goes +52.9 -> +61.4, and 2022-2026 goes +69.5 -> +74.5 - and it raises the worst
year from +19.6 to +25.2 while keeping position MDD at -4.60, inside the -5 line.
A change that improves the untouched window is not a fit to the recent one.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
NEW = dict(brake=((-0.006, 0.50), (-0.012, 0.25)), liq=0.10, gap_max=0.04,
           gap_max_long=0.08, exposure=1.00, spread=T.SPREAD)
OLD = dict(NEW); OLD["brake"] = ((-0.006, 0.30), (-0.012, 0.12))

for label, cfg in (("現行 30/12", OLD), ("候選 50/25", NEW)):
    r = T.run(**cfg)
    y = r["yearly"]; yrs = sorted(y)
    rets = [y[k] / CAP0 * 100 for k in yrs]
    print("\n=== %s ===" % label)
    print("  13yr %+.1f%%  MDD %.2f%%  最差年 %+.1f%%  %.1f 筆/日  煞車 %.1f%%"
          % (np.mean(rets), r["mdd"], min(rets), r["per_day"], r["brake_pct"]))
    for lo, hi in ((2014, 2021), (2022, 2026)):
        s = [y[k] / CAP0 * 100 for k in yrs if lo <= k <= hi]
        print("  %d-%d 年均 %+.1f%%" % (lo, hi, sum(s) / len(s)))
    if "候選" in label:
        mon = r["monthly"]; tot = 0.0
        print("  %-6s %8s %9s %8s %8s" % ("年", "報酬%", "對450萬", "筆數", "勝率"))
        for k in yrs:
            n = sum(v[1] for m, v in mon.items() if m[0] == k)
            w = sum(v[2] for m, v in mon.items() if m[0] == k)
            tot += y[k]
            print("  %-6d %+7.1f %8.0f萬 %8d %7.1f%%"
                  % (k, y[k] / CAP0 * 100, y[k] / 10000, n,
                     w / n * 100 if n else 0.0))
        print("  13 年總獲利 %.0f 萬" % (tot / 10000))
    print("  多空：SHORT %d 筆 %+.0f 萬｜LONG %d 筆 %+.0f 萬"
          % (r["dir_n"]["SHORT"], r["dir_y"]["SHORT"] / 10000,
             r["dir_n"]["LONG"], r["dir_y"]["LONG"] / 10000), flush=True)
