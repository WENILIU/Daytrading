# -*- coding: utf-8 -*-
r"""The other direction: a tighter brake for the no-stop regime.

The first sweep only moved the brake shallower (50/25 -> 70/40), which raised
CAGR and raised drawdown monotonically - so 50/25 is already the mildest thing
on that axis and cannot reach -5%. The remaining direction is tighter: cut
earlier, cut deeper. Same discipline: choose on 2014-2021, report 2022-2026.
"""
import warnings; warnings.filterwarnings("ignore")
import v13_target as T

base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08,
            nosl=True, spread=0.00105)
GRID = [((-.006, .45), (-.012, .22)), ((-.006, .40), (-.012, .20)),
        ((-.006, .35), (-.012, .15)), ((-.006, .30), (-.012, .12)),
        ((-.004, .50), (-.008, .25)), ((-.005, .50), (-.010, .25)),
        ((-.004, .40), (-.008, .20)), ((-.006, .50), (-.012, .25), )]
print("煞車（回撤閾值→剩餘倉位）              13yr    2014-21   2022-26     MDD    最差年")
for brake in GRID:
    y = T.run(**dict(base, brake=brake))
    yr = y["yearly"]; ks = sorted(yr)
    v = [yr[k] / T.CAP0 * 100 for k in ks]
    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    lab = " ".join("%.3f->%.0f%%" % (t, m * 100) for t, m in brake)
    flag = "  <== 達標" if (y["mdd"] >= -5.0 and avg(2022, 2026) >= 100.0) else ""
    print("%-38s %+6.1f%%  %+7.1f%%  %+7.1f%%  %6.2f%%  %+6.1f%%%s"
          % (lab, sum(v) / len(v), avg(2014, 2021), avg(2022, 2026), y["mdd"], min(v), flag), flush=True)
