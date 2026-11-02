# -*- coding: utf-8 -*-
r"""The order count is a risk lever, not just a throughput limit.

v19_pinfix3.py found it by accident: at gap_max 0.030, order_cap 30 -> 20 moved the
position MDD from -5.88 pct to -4.05 pct and gave up only 3 pp of the recent return.
That is not proportional de-risking. The worst day in this book is one day with ~30
trades in it (2021-05-18: 30 trades, 29 SHORT), and a count cap removes the LOWEST
ranked ones - on a squeeze morning those are the marginal, worst shorts - so it cuts
the tail faster than it cuts the mean.

Everything else about that day said "no pre-trade filter works" (STRATEGY_v13.md,
"為什麼 MDD 只有一天" / v19_dircap / v19_lock2). A count cap is different in kind: it
does not need to predict the day, it just refuses to be maximally concentrated in
whatever direction the day turns out to punish. It is also the one lever live already
has (max_orders_per_day), and it reduces the 22-orders-per-day execution risk instead
of adding to it.

Map the frontier: for each gap ceiling, what is the largest book that still holds
MDD inside -5 pct.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00,
            cost_mode="measured", gap_max_long=0.08, spread=0.00105)
GP = dict(nosl=True, brake=((-0.008, .50), (-0.016, .25)))
A_ = dict(nosl=False, brake=((-0.006, .50), (-0.012, .25)))
CASES = []
for cap in (0.030, 0.035, 0.040):
    for oc in (18, 20, 22, 25, 30):
        CASES.append(("G+ gap<=%.3f cap=%d" % (cap, oc), dict(GP, gap_max=cap, order_cap=oc)))
for oc in (20, 25, 30):
    CASES.append(("A  gap<=0.030 cap=%d" % oc, dict(A_, gap_max=0.030, order_cap=oc)))

HDR = "%-26s %+6s %+8s %+8s %7s %7s %7s %6s" % (
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
    flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ("  <- MDD 內" if m >= -5.0 else "")
    print("%-26s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %6.1f%% %6.1f%s"
          % (tag, a, o, r, m, w, pinrate, y["per_day"], flag), flush=True)
    rows.append(dict(case=tag, all=a, old=o, recent=r, mdd=m, worst=w,
                     pinrate=pinrate, per_day=y["per_day"], n=y["n"]))
pd.DataFrame(rows).to_csv("_ordercap.csv", index=False)
ok = [x for x in rows if x["mdd"] >= -5.0]
print("\nMDD 在 -5%% 以內的最佳：%s" % (max(ok, key=lambda x: x["recent"])["case"] if ok else "無"), flush=True)
print("saved _ordercap.csv", flush=True)
