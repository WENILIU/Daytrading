# -*- coding: utf-8 -*-
r"""Re-measure the two levers that the corrected pin cost changes the answer to.

The flat 0.00747 understated the SHORT side ~3x (v19_pincalc.py: the conditional
cost of being pinned is SHORT -3.149 pct). Two consequences:

1. The SHORT gap ceiling. v19_pin_gap.py measured the lock RATE by band: 1.5-3 pct
   25.5 pct, 3-4 pct 40.3 pct. That gradient was always there; what changed is what
   it is worth. v19_capsl.py concluded "keep 0.04" against the old cost. Re-run it.
2. dir_cap. It was rejected because the one-sided squeeze day cost less than the
   return it gave up. The squeeze day is exactly the day the pin cost lands, and it
   just tripled. Re-test it, do not assume the old verdict holds.

Both on G+ (the best config), plus the three caps around live's 0.04 on A.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
PS, PL = 0.03149, 0.0
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00, order_cap=30,
            cost_mode="measured", gap_max_long=0.08, spread=0.00105,
            pin_short=PS, pin_long=PL)
GP = dict(nosl=True, brake=((-0.008, .50), (-0.016, .25)))
A_ = dict(nosl=False, brake=((-0.006, .50), (-0.012, .25)))

CASES = []
for tag, cap in (("0.020", .020), ("0.025", .025), ("0.030", .030), ("0.035", .035),
                 ("0.040 現行", .040), ("0.050", .050), ("0.060", .060), ("無上限", None)):
    CASES.append(("G+ " + tag, dict(GP, gap_max=cap)))
for tag, cap in (("0.030", .030), ("0.040 現行", .040), ("0.050", .050)):
    CASES.append(("A  " + tag, dict(A_, gap_max=cap)))
for dc in (0.5, 0.7):
    CASES.append(("G+ 無上限 dir_cap=%.1f" % dc, dict(GP, gap_max=None, dir_cap=dc)))

HDR = ("%-24s %+6s %+8s %+8s %7s %7s %7s %7s %6s" %
       ("配置", "13yr", "2014-21", "2022-26", "MDD", "最差年", "鎖價率", "筆/日", "曝險"))
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
    print("%-24s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %6.1f%% %7.1f %6.1f%s"
          % (tag, a, o, r, m, w, pinrate, y["per_day"], y["expo"], flag), flush=True)
    rows.append(dict(case=tag, all=a, old=o, recent=r, mdd=m, worst=w,
                     pinrate=pinrate, per_day=y["per_day"], expo=y["expo"], n=y["n"]))
    print("      逐年%：", " ".join("%d %+.0f" % (k, x) for k, x in zip(ks, v)), flush=True)
pd.DataFrame(rows).to_csv("_pinfix_levers.csv", index=False)
print("saved _pinfix_levers.csv", flush=True)
