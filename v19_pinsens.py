# -*- coding: utf-8 -*-
r"""Does widening the SHORT gap cap survive when the pin cost is priced honestly?

v19_pin_gap.py measured the expected cost of a trade that ends on a price limit,
by the gap that produced the signal, on the SHORT side only (the side that has
to buy back):

  1.5-3 pct   n=550  locked 25.5 pct  expected -0.799 pct
  3-4   pct   n=196  locked 40.3 pct  expected -1.275 pct

There is no measured SHORT row above 4 pct - the strategy has never traded one
that reached a price limit - so every config with the cap above 4 pct is charged
the flat 0.747 pct average for a region where the measured gradient says the cost
roughly doubles per band. This script prices that instead of arguing about it:
the same four caps, three pin costs, and the question is which cap still wins
when the tail is charged at the measured large-gap value.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import v13_target as T

CAP = T.CAP0
BRAKE = ((-0.008, .50), (-0.016, .25))
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00, order_cap=30,
            cost_mode="measured", gap_max_long=0.08, spread=0.00105,
            nosl=True, brake=BRAKE)
PINS = [("平均 0.747", 0.00747), ("3-4% 實測 1.275", 0.01275), ("兩倍 1.590", 0.01590)]
CAPS = [("現行 SHORT<=0.04", 0.04), ("SHORT<=0.06", 0.06), ("SHORT<=0.08", 0.08),
        ("SHORT 無上限", None)]

HDR = "%-20s %-18s %+6s %+8s %+8s %7s %7s %6s" % (
    "gap 上限", "鎖價成本", "13yr", "2014-21", "2022-26", "MDD", "最差年", "筆/日")
rows = []
print(HDR, flush=True)
for cap_tag, cap in CAPS:
    for pin_tag, pin in PINS:
        y = T.run(**dict(base, gap_max=cap, pin_penalty=pin))
        yr = y["yearly"]; ks = sorted(yr)
        v = [yr[k] / CAP * 100 for k in ks]

        def avg(a, b):
            s = [x for k, x in zip(ks, v) if a <= k <= b]
            return sum(s) / len(s)
        a, o, r, m, w = (sum(v) / len(v), avg(2014, 2021), avg(2022, 2026),
                         y["mdd"], min(v))
        flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ""
        print("%-20s %-18s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %6.1f%s"
              % (cap_tag, pin_tag, a, o, r, m, w, y["per_day"], flag), flush=True)
        rows.append(dict(cap=cap_tag, pin=pin_tag, all=a, old=o, recent=r, mdd=m,
                         worst=w, per_day=y["per_day"]))
    print(flush=True)
pd.DataFrame(rows).to_csv("_pin_sens.csv", index=False)
print("saved _pin_sens.csv", flush=True)
