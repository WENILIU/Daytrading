# -*- coding: utf-8 -*-
r"""The numbers after two corrections, and the brake that fits them.

Two things changed under every number quoted before this run:

1. pin_penalty - a trade that ends pinned on a price limit cannot be cleared at
   13:20, and the measured expected cost of that is -0.747 pct per such trade.
2. the brake tiers - v13_target tested the shallow threshold first, and since the
   deep threshold is always shallower in value, the deep tier was unreachable.
   The backtest was simulating a LOOSER brake than live actually runs
   (gap_fade_auto.py:2664 checks dd_th2 before dd_th1 and is correct).

So the published A and G numbers were measured against a brake that is not the
one live uses, and against a cost that is not real. Both are now in. Choose on
2014-2021, report 2022-2026. Target: recent five years >= 100 pct, position MDD
inside -5 pct, on the broker's 4.5M line with no financing.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import v13_target as T

CAP = T.CAP0
PIN = 0.00747
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08, spread=0.00105)
CASES = [("A 現行（SL 4%、煞車 50/25）", dict(nosl=False, brake=((-0.006, .50), (-0.012, .25)))),
         ("G 不設停損（煞車 45/22）", dict(nosl=True, brake=((-0.006, .45), (-0.012, .22))))]

def sm(y):
    yr = y["yearly"]; ks = sorted(yr)
    v = [yr[k] / CAP * 100 for k in ks]
    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    return sum(v) / len(v), avg(2014, 2021), avg(2022, 2026), y["mdd"], min(v), y["n_pin"], sum(yr.values())

print("=== 修正後（雙層煞車真的會分層 + 鎖價成本）===")
print("配置                                13yr   2014-21  2022-26     MDD   最差年   總獲利")
for tag, kw in CASES:
    for pin, lab in ((0.0, "未計鎖價"), (PIN, "已計鎖價")):
        a, o, r, m, w, np_, tot = sm(T.run(**dict(base, **kw, pin_penalty=pin)))
        print("%-34s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %7.0f萬  [%s]"
              % (tag, a, o, r, m, w, tot / 1e4, lab), flush=True)

print("\n=== 用修正後的煞車重新校準（G，已計鎖價成本）===")
print("煞車                                13yr   2014-21  2022-26     MDD   最差年   筆/日")
GRID = [((-0.006, .45), (-0.012, .22)), ((-0.006, .40), (-0.012, .20)),
        ((-0.006, .35), (-0.012, .15)), ((-0.006, .45), (-0.012, .10)),
        ((-0.006, .50), (-0.012, .15)), ((-0.006, .50), (-0.012, .25)),
        ((-0.006, .55), (-0.012, .20)), ((-0.006, .60), (-0.012, .25)),
        ((-0.008, .50), (-0.016, .25)), ((-0.004, .45), (-0.008, .20))]
rows = []
for brake in GRID:
    y = T.run(**dict(base, nosl=True, brake=brake, pin_penalty=PIN))
    a, o, r, m, w, np_, tot = sm(y)
    lab = " ".join("%.3f->%.0f%%" % (t, s * 100) for t, s in brake)
    flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ""
    print("%-36s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %5.1f%s"
          % (lab, a, o, r, m, w, y["per_day"], flag), flush=True)
    rows.append(dict(brake=lab, all=a, old=o, recent=r, mdd=m, worst_year=w, per_day=y["per_day"]))
pd.DataFrame(rows).to_csv("_brake_fixed.csv", index=False)
print("\nsaved _brake_fixed.csv")
