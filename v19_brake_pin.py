# -*- coding: utf-8 -*-
r"""Re-tune the brake against the honest cost.

The brake 45/22 was chosen when the book still assumed a pinned trade clears at
the limit price. It now has to pay the measured expected cost of not clearing
(0.747 pct per trade that ends on a limit: 32.3 pct are genuinely pinned, and
carrying those costs -2.311 pct). A cost that was missing is a change of regime,
so the parameter chosen under the old one is not automatically still the answer.

Same discipline as every other sweep here: choose on 2014-2021, report 2022-2026.
The target is CAGR >= 100 pct on the recent five years with position MDD inside
-5 pct, on a 4.5M line with no financing.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import v13_target as T

CAP = T.CAP0
PIN = 0.00747
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08, spread=0.00105,
            nosl=True, pin_penalty=PIN)
GRID = [((-0.006, .45), (-0.012, .22)), ((-0.006, .40), (-0.012, .20)),
        ((-0.006, .35), (-0.012, .15)), ((-0.006, .30), (-0.012, .12)),
        ((-0.005, .40), (-0.010, .22)), ((-0.004, .45), (-0.008, .22)),
        ((-0.004, .35), (-0.008, .15)), ((-0.003, .40), (-0.006, .15)),
        ((-0.006, .25), (-0.012, .10)), ((-0.008, .50), (-0.016, .30))]
print("煞車（回撤閾值→剩餘倉位）              13yr    2014-21  2022-26     MDD   最差年   筆/日")
rows = []
for brake in GRID:
    y = T.run(**dict(base, brake=brake))
    yr = y["yearly"]; ks = sorted(yr)
    v = [yr[k] / CAP * 100 for k in ks]

    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    lab = " ".join("%.3f->%.0f%%" % (t, m * 100) for t, m in brake)
    old, rec = avg(2014, 2021), avg(2022, 2026)
    flag = "  <== 達標" if (y["mdd"] >= -5.0 and rec >= 100.0) else ""
    print("%-38s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %5.1f%s"
          % (lab, sum(v) / len(v), old, rec, y["mdd"], min(v), y["per_day"], flag), flush=True)
    rows.append(dict(brake=lab, all=sum(v) / len(v), old=old, recent=rec,
                     mdd=y["mdd"], worst_year=min(v), per_day=y["per_day"]))
pd.DataFrame(rows).to_csv("_brake_pin.csv", index=False)
print("\nsaved _brake_pin.csv")
