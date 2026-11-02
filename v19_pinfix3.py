# -*- coding: utf-8 -*-
r"""Close the two remaining levers against the corrected pin cost.

The gap-cap sweep (v19_pinfix2.py) showed the position MDD floor for this family is
about -5.8 pct, not -5.0: tightening the cap lowers the pin RATE from 5.2 pct to
2.6 pct and the MDD barely moves, so the pin cost adds ~1.6 pp to an event that was
already -5.00. Two ways that event could still be attacked:

  zt_min_dist  - skip signals whose price limit is close. v19_ztdist.py says this
                 has almost no teeth on the SHORT side (0.07 pct of traded signals
                 are under 2 pct away, 2.25 pct under 5 pct), so it is measured here
                 only to close it with a number rather than an argument.
  order_cap    - the worst day is one day with ~30 trades in it. Fewer orders per
                 day caps that directly. "only the top K" was rejected before the
                 pin cost tripled; re-test rather than inherit the verdict.

Row 1 is a regression check: with no pin arguments at all the run must reproduce
the corrected G+ numbers (+74.3 / +83.6 / -6.59), which is what "the honest cost is
now the default" has to mean.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.030, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08, spread=0.00105,
            nosl=True, brake=((-0.008, .50), (-0.016, .25)))
CASES = [("G+ 0.030 預設成本(回歸)", dict()),
         ("G+ 0.030 zt<4% 跳過", dict(zt_min_dist=0.04)),
         ("G+ 0.030 zt<5% 跳過", dict(zt_min_dist=0.05)),
         ("G+ 0.030 order_cap=20", dict(order_cap=20)),
         ("G+ 0.030 order_cap=15", dict(order_cap=15)),
         ("G+ 0.030 order_cap=10", dict(order_cap=10))]

HDR = "%-28s %+6s %+8s %+8s %7s %7s %7s %7s %6s" % (
    "配置", "13yr", "2014-21", "2022-26", "MDD", "最差年", "鎖價率", "筆/日", "曝險")
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
    flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ""
    print("%-28s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %6.1f%% %7.1f %6.1f%s"
          % (tag, a, o, r, m, w, pinrate, y["per_day"], y["expo"], flag), flush=True)
    print("      逐年%：", " ".join("%d %+.0f" % (k, x) for k, x in zip(ks, v)), flush=True)
    print("      zt 跳過 %d 筆" % y["n_ztskip"], flush=True)
    rows.append(dict(case=tag, all=a, old=o, recent=r, mdd=m, worst=w,
                     pinrate=pinrate, per_day=y["per_day"], expo=y["expo"],
                     ztskip=y["n_ztskip"], n=y["n"]))
pd.DataFrame(rows).to_csv("_pinfix_tail.csv", index=False)
print("saved _pinfix_tail.csv", flush=True)
