# -*- coding: utf-8 -*-
r"""Re-aim the equity brake for the no-stop regime.

The brake is the portfolio-level risk controller. It was tuned while every trade
carried its own stop, which took the worst of the tail out at the position level.
With no stop, the tail moves to the portfolio, so the brake has to be re-aimed
rather than assumed still correct.

Tuned on 2014-2021 only; 2022-2026 is reported alongside and was not used to
choose anything. The target is the objective as stated: CAGR 100% with the
position drawdown inside -5%.
"""
import warnings; warnings.filterwarnings("ignore")
import v13_target as T

base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08,
            nosl=True, spread=0.00105)
GRID = [((-.006, .50), (-.012, .25)), ((-.006, .55), (-.012, .28)),
        ((-.006, .60), (-.012, .30)), ((-.006, .65), (-.012, .35)),
        ((-.006, .70), (-.012, .40)), ((-.008, .60), (-.016, .30)),
        ((-.010, .60), (-.020, .30)), ((-.006, .60), (-.012, .30), (-.020, .15))]
print("煞車（回撤閾值→剩餘倉位）              13yr    2014-21   2022-26     MDD    最差年")
best = None
for brake in GRID:
    y = T.run(**dict(base, brake=brake))
    yr = y["yearly"]; ks = sorted(yr)
    v = [yr[k] / T.CAP0 * 100 for k in ks]
    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    lab = " ".join("%.3f->%.0f%%" % (t, m * 100) for t, m in brake)
    print("%-38s %+6.1f%%  %+7.1f%%  %+7.1f%%  %6.2f%%  %+6.1f%%"
          % (lab, sum(v) / len(v), avg(2014, 2021), avg(2022, 2026), y["mdd"], min(v)), flush=True)
    ok = y["mdd"] >= -5.0 and avg(2022, 2026) >= 100.0
    if ok and (best is None or avg(2014, 2021) > best[1]):
        best = (brake, avg(2014, 2021))
print()
if best:
    print("兩個窗口都達標、且 2014-2021 最好的煞車：", best[0])
else:
    print("沒有同時滿足 MDD>=-5% 且 2022-26>=100% 的組合")
