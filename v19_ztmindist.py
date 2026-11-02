# -*- coding: utf-8 -*-
r"""Exclude positions entered too close to the price limit (zt_min_dist).

The pin split showed near-limit shorts are net-negative (-3.4 to -10.5 pct), yet the
engine BOOSTS them x10 (zt_dist<1.5 pct). zt_min_dist skips a signal whose distance to
the limit is below a threshold - it removes exactly the population the x10 was amplifying,
so it fixes the backwards sizing by not taking those trades at all. All runs carry the
honest pin cost (price 3.149 + tax 0.15 + borrow 30pct x2d = 3.46 pct).
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
PIN = 0.03149 + 0.0015 + 0.30 * 2 / 365.0
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00,
            gap_max_long=0.08, spread=0.00105, cost_mode="measured",
            brake=((-0.008, .50), (-0.016, .25)), gap_max=0.040, order_cap=20,
            nosl=True, pin_short=PIN, pin_long=0.0)

def summarize(tag, y):
    yr = y["yearly"]; ks = sorted(yr); v = [yr[k] / CAP * 100 for k in ks]
    recent = sum(x for k, x in zip(ks, v) if 2022 <= k <= 2026) / len([k for k in ks if 2022 <= k <= 2026])
    m = y["mdd"]; pinS = y["n_pin_dir"].get("SHORT", 0)
    print("%-30s 2022-26 %+7.1f%%  MDD %6.2f%%  比值 %5.1f  筆/日 %4.1f  總筆 %6d  鎖停SHORT %5d  跳過 %6d"
          % (tag, recent, m, recent/abs(m), y["per_day"], y["n"], pinS, y["n_ztskip"]), flush=True)
    return dict(tag=tag, recent=recent, mdd=m, ratio=recent/abs(m), per_day=y["per_day"],
                n=y["n"], pinS=pinS, ztskip=y["n_ztskip"])

rows = []
print("honest pin cost = %.4f" % PIN, flush=True)
rows.append(summarize("honest B (基準)", T.run(**base)))
for z in [0.015, 0.03, 0.05, 0.08]:
    rows.append(summarize("zt_min_dist >= %.3f" % z, T.run(**dict(base, zt_min_dist=z))))
pd.DataFrame(rows).to_csv("_ztmindist.csv", index=False)
print("saved _ztmindist.csv", flush=True)
