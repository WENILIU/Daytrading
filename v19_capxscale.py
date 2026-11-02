# -*- coding: utf-8 -*-
r"""Daily notional cap x order size: the one 2-D lever left, and it is not leverage.

Last round I reported "scale is pure leverage" and stopped. That was half right and
it hid the actual lever. v13_target has two different knobs that were treated as one:

  size_scale  multiplies every order            -> leverage (measured: p90 exposure is
                                                  already 99.4 pct, so it lifts the
                                                  mean and the tail together)
  exposure    caps the DAY's total notional     -> never swept below 1.0

They are not the same thing. The drawdown here is a single one-direction day at ~99
pct deployment while the median day sits at 21 pct. A cap on the day's total cuts the
99 pct day by up to 40 pct and leaves the median day untouched - it is a change in the
SHAPE of the exposure distribution, not its level. Pair it with a larger order size and
the quiet mornings get back the volume the cap took from the loud ones. That is the
only mechanism in this strategy that can raise return per unit of drawdown, which is
what a 100 pct / -5 pct target actually asks for (ratio 20.0; the book is at 17.0).

Sweeping the grid, reporting the ratio, and sorting by return inside MDD >= -5.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.040, gap_scale=1.0, order_cap=20,
            cost_mode="measured", gap_max_long=0.08, spread=0.00105,
            nosl=True, brake=((-0.008, .50), (-0.016, .25)))
CASES = []
for expo in (1.0, 0.8, 0.7, 0.6, 0.5):
    for sc in (1.0, 1.5, 2.0):
        if expo == 1.0 and sc == 1.0:
            continue                      # already measured: +81.8 / -4.80
        CASES.append((expo, sc))

HDR = "%-22s %+6s %+8s %+8s %7s %7s %6s %s" % (
    "曝險上限 x 單筆倍數", "13yr", "2014-21", "2022-26", "MDD", "比值", "筆/日", "曝險 p50/p90/max")
rows = []
print(HDR, flush=True)
for expo, sc in CASES:
    y = T.run(**dict(base, exposure=expo, size_scale=sc))
    yr = y["yearly"]; ks = sorted(yr)
    v = [yr[k] / CAP * 100 for k in ks]

    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    a, o, r, m, w = (sum(v) / len(v), avg(2014, 2021), avg(2022, 2026), y["mdd"], min(v))
    ratio = r / abs(m)
    ep = y["expo_pct"]
    dist = "%5.1f/%5.1f/%5.1f" % (ep.get(50, 0), ep.get(90, 0), y["expo_max"])
    flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ("  <- MDD內" if m >= -5.0 else "")
    print("cap %.1f x scale %.1f      %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %6.1f %6.1f %s%s"
          % (expo, sc, a, o, r, m, ratio, y["per_day"], dist, flag), flush=True)
    rows.append(dict(expo_cap=expo, scale=sc, all=a, old=o, recent=r, mdd=m, worst=w,
                     ratio=ratio, per_day=y["per_day"], p50=ep.get(50), p90=ep.get(90),
                     pmax=y["expo_max"]))
df = pd.DataFrame(rows)
df.to_csv("_cap_x_scale.csv", index=False)
print("\n--- MDD 在 -5%% 以內，按近五年報酬排序 ---", flush=True)
ok = df[df.mdd >= -5.0].sort_values("recent", ascending=False)
print(ok[["expo_cap", "scale", "recent", "mdd", "ratio", "per_day", "p50", "p90"]].to_string(index=False), flush=True)
print("\n--- 比值最高（目標要的是 20.0）---", flush=True)
print(df.sort_values("ratio", ascending=False).head(8)[["expo_cap", "scale", "recent", "mdd", "ratio"]].to_string(index=False), flush=True)
print("saved _cap_x_scale.csv", flush=True)
