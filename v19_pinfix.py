# -*- coding: utf-8 -*-
r"""Re-run the published baselines with the pin cost charged per side.

The flat pin_penalty 0.00747 was the UNconditional mean over every trade that
touched a price limit (0.323 x 2.311 pct), but v13_target only ever charged it to
the trades that ARE pinned. The conditional value is SHORT -3.149 pct (n=219) and
LONG +0.349 pct (n=69, unstable by year, so charged as 0 rather than as a credit).
Every number published before this correction is on the wrong cost.

Same configs, same costs, one changed constant. A is what live runs; G is the
no-stop variant that clears the target; G-wide is G with the brake loosened.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
PIN_OLD = 0.00747
PIN_S, PIN_L = 0.03149, 0.0
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08, spread=0.00105)
CASES = [
    ("A  SL 4%  煞車50/25", dict(nosl=False, brake=((-0.006, .50), (-0.012, .25)))),
    ("G  不設停損 煞車45/22", dict(nosl=True,  brake=((-0.006, .45), (-0.012, .22)))),
    ("G+ 不設停損 煞車50/25放寬", dict(nosl=True, brake=((-0.008, .50), (-0.016, .25)))),
]
PINS = [("舊 平均0.747(兩邊)", dict(pin_penalty=PIN_OLD)),
        ("新 SHORT3.149/LONG0", dict(pin_short=PIN_S, pin_long=PIN_L))]

HDR = ("%-26s %-22s %+6s %+8s %+8s %7s %7s %7s %6s %6s" %
       ("配置", "鎖價成本", "13yr", "2014-21", "2022-26", "MDD", "最差年", "鎖價筆", "S/L筆", "筆/日"))
rows = []
print(HDR, flush=True)
for tag, cfg in CASES:
    for pt, pk in PINS:
        y = T.run(**dict(base, **cfg, **pk))
        yr = y["yearly"]; ks = sorted(yr)
        v = [yr[k] / CAP * 100 for k in ks]

        def avg(a, b):
            s = [x for k, x in zip(ks, v) if a <= k <= b]
            return sum(s) / len(s)
        a, o, r, m, w = (sum(v) / len(v), avg(2014, 2021), avg(2022, 2026),
                         y["mdd"], min(v))
        npd = y["n_pin_dir"]
        flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ""
        print("%-26s %-22s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %7d %3d/%-3d %6.1f%s"
              % (tag, pt, a, o, r, m, w, y["n_pin"], npd["SHORT"], npd["LONG"],
                 y["per_day"], flag), flush=True)
        rows.append(dict(case=tag, pin=pt, all=a, old=o, recent=r, mdd=m, worst=w,
                         n_pin=y["n_pin"], pin_s=npd["SHORT"], pin_l=npd["LONG"],
                         n=y["n"], per_day=y["per_day"]))
        print("      逐年%：", " ".join("%d %+.0f" % (k, x) for k, x in zip(ks, v)), flush=True)
    print(flush=True)
pd.DataFrame(rows).to_csv("_pin_fixed.csv", index=False)
print("saved _pin_fixed.csv", flush=True)
