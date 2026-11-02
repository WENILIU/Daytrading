# -*- coding: utf-8 -*-
r"""The decisive question: is 100 pct reachable AT ALL at 450 wan, zero margin?

Every mechanism is now measured except one combination. The best ratio found anywhere
is gap 0.030 / order cap 20: +77.6 pct recent at -4.05 pct MDD (ratio 19.2). The
auction entry is worth +9.3 pp and slightly improves the drawdown. Nothing has run
those two together, and that is the only point in the space that could plausibly
clear 100 pct at -5 pct.

This is the ceiling test, so cost_mode="auction" throughout: it assumes the 08:59
decision is made on an indicative price that equals the open. If even this grid cannot
put 100 pct inside -5 pct, then the target is not a tuning problem and the answer to
the objective is "not reachable on this strategy at this account size" - which is a
different, and honest, kind of answer.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00,
            cost_mode="auction", gap_max_long=0.08, spread=0.00105,
            nosl=True, brake=((-0.008, .50), (-0.016, .25)))
CASES = []
for cap in (0.030, 0.035, 0.040):
    for oc in (20, 22, 25):
        CASES.append((cap, oc))

HDR = "%-24s %+6s %+8s %+8s %7s %7s %6s" % (
    "A 臂天花板 gap上限 x 筆數", "13yr", "2014-21", "2022-26", "MDD", "比值", "筆/日")
rows = []
print(HDR, flush=True)
for cap, oc in CASES:
    y = T.run(**dict(base, gap_max=cap, order_cap=oc))
    yr = y["yearly"]; ks = sorted(yr)
    v = [yr[k] / CAP * 100 for k in ks]

    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    a, o, r, m, w = (sum(v) / len(v), avg(2014, 2021), avg(2022, 2026), y["mdd"], min(v))
    ratio = r / abs(m)
    flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ("  <- MDD內" if m >= -5.0 else "")
    print("gap %.3f oc=%-3d       %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %6.1f %6.1f%s"
          % (cap, oc, a, o, r, m, ratio, y["per_day"], flag), flush=True)
    rows.append(dict(gap_max=cap, order_cap=oc, all=a, old=o, recent=r, mdd=m, worst=w,
                     ratio=ratio, per_day=y["per_day"]))
df = pd.DataFrame(rows)
df.to_csv("_arm_a_grid.csv", index=False)
ok = df[df.mdd >= -5.0].sort_values("recent", ascending=False)
print("\n--- A 臂天花板下，MDD 在 -5%% 內按報酬排序（目標 100%%）---", flush=True)
print(ok[["gap_max", "order_cap", "recent", "mdd", "ratio", "per_day"]].to_string(index=False), flush=True)
best = ok.iloc[0] if len(ok) else None
if best is not None:
    print("\n最高近五年報酬（MDD 內）：%.1f%% @ gap %.3f oc %d，MDD %.2f%%，比值 %.1f"
          % (best.recent, best.gap_max, best.order_cap, best.mdd, best.ratio), flush=True)
    print("距離目標：%.1f pp" % (100.0 - best.recent), flush=True)
print("saved _arm_a_grid.csv", flush=True)
