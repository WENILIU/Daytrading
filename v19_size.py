# -*- coding: utf-8 -*-
r"""Same signals, bigger orders: does the 36 pct average deployment hide free return?

The book runs at 36 pct of the 450 wan on average and 99 pct on the worst day. If
that distribution is bimodal - quiet mornings with few signals, loud mornings that
already spend everything - then multiplying the per-order size raises the quiet days
and cannot touch the loud ones, because those are stopped by the cash, not by the
weight. That is the one asymmetry left after the pin correction took the drawdown
headroom away.

scale multiplies the model weight (v13_sizing rule "scale"); exposure is a ceiling
on the day's total. They are different levers and only the second has ever been
swept, and only upward (v13_gates.py: scale 1.5/2.0/5.0). Nothing has measured
"bigger orders on the days that were never near a ceiling".

Watch the exposure percentiles: if p50 rises while p99 stays put, the mechanism is
real. If p99 rises too, the tail moved with it and this is just leverage.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.040, gap_scale=1.0, exposure=1.00,
            order_cap=20, cost_mode="measured", gap_max_long=0.08, spread=0.00105)
GP = dict(nosl=True, brake=((-0.008, .50), (-0.016, .25)))
A_ = dict(nosl=False, brake=((-0.006, .50), (-0.012, .25)))
CASES = [("G+ scale=1.0 (基準)", dict(GP, **{}))]
for sc in (1.5, 2.0, 3.0, 5.0):
    CASES.append(("G+ scale=%.1f" % sc, dict(GP, size_scale=sc)))
for sc in (1.5, 2.0):
    CASES.append(("A  scale=%.1f" % sc, dict(A_, size_scale=sc)))

HDR = "%-22s %+6s %+8s %+8s %7s %7s %s" % (
    "配置", "13yr", "2014-21", "2022-26", "MDD", "最差年", "曝險 p50/p90/p99/max")
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
    ep = y["expo_pct"]
    dist = " %5.1f/%5.1f/%5.1f/%5.1f" % (ep.get(50, 0), ep.get(90, 0), ep.get(99, 0), y["expo_max"])
    flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ("  <- MDD內" if m >= -5.0 else "")
    print("%-22s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%%%s%s"
          % (tag, a, o, r, m, w, dist, flag), flush=True)
    print("      逐年%：", " ".join("%d %+.0f" % (k, x) for k, x in zip(ks, v)), flush=True)
    rows.append(dict(case=tag, all=a, old=o, recent=r, mdd=m, worst=w,
                     expo=y["expo"], p50=ep.get(50), p90=ep.get(90), p99=ep.get(99),
                     pmax=y["expo_max"], per_day=y["per_day"], n=y["n"]))
pd.DataFrame(rows).to_csv("_size_scale.csv", index=False)
print("saved _size_scale.csv", flush=True)
