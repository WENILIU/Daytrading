# -*- coding: utf-8 -*-
r"""Is the opening auction actually the road to 100 pct, on the corrected book?

STRATEGY_v13.md / LIVE_READINESS.md 11.27 carry "+12.7 pp for entering via the
auction instead of at 09:01", measured 2026-11-01. But the entry-cost table that
v13_target actually charges says the opposite on the side that dominates this book:
ENTRY_COST[("SHORT", 0.00)] = -0.000942, i.e. a 09:01 entry BEATS the opening print
by 0.094 pct for a short with a gap under 5 pct. Those two statements cannot both be
true, and one of them is the reason the last 18 pp of the target is being treated as
reachable.

Settle it on the book the target is quoted from: same signals, same sizing, same
brake, same order cap 20, same corrected pin cost - only the entry charge differs.
cost_mode="auction" charges nothing, which is the ceiling of arm A (it assumes the
08:59 decision was made on an indicative price that matched the open; the gap between
those is what preopen_probe.py exists to measure). If even the ceiling does not reach
100 pct, the auction is not the missing piece and the docs have to say so.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.040, gap_scale=1.0, exposure=1.00,
            order_cap=20, gap_max_long=0.08, spread=0.00105)
GP = dict(nosl=True, brake=((-0.008, .50), (-0.016, .25)))
A_ = dict(nosl=False, brake=((-0.006, .50), (-0.012, .25)))
CASES = [("G+ B 臂 09:01（現在 live 對齊的）", dict(GP, cost_mode="measured")),
         ("G+ A 臂 競價上限（不付進場成本）", dict(GP, cost_mode="auction")),
         ("A  B 臂 09:01", dict(A_, cost_mode="measured")),
         ("A  A 臂 競價上限", dict(A_, cost_mode="auction"))]

HDR = "%-34s %+6s %+8s %+8s %7s %7s %7s" % (
    "配置", "13yr", "2014-21", "2022-26", "MDD", "最差年", "筆/日")
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
    flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ("  <- MDD內" if m >= -5.0 else "")
    print("%-34s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %6.1f%s"
          % (tag, a, o, r, m, w, y["per_day"], flag), flush=True)
    print("      逐年%：", " ".join("%d %+.0f" % (k, x) for k, x in zip(ks, v)), flush=True)
    rows.append(dict(case=tag, all=a, old=o, recent=r, mdd=m, worst=w, per_day=y["per_day"]))
pd.DataFrame(rows).to_csv("_arm_a.csv", index=False)
print("saved _arm_a.csv", flush=True)
