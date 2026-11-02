# -*- coding: utf-8 -*-
r"""How much of A->G is the stop WIDTH, and how much is having no stop at all.

The decision in front of Weni is not "stop vs no stop". He has already said he
does not want to carry an overnight short, and he has already said the 40 pct
stop-out share looks fixable. Both are the same question: where on the width
axis does the strategy stop selling its own alpha?

SLO is a module global in v13_engine that exit_of_legal reads at call time, so
patching it here changes execution only - the signal, the model, the sizing and
the cost model are untouched. Same discipline as every other sweep this round:
choose on 2014-2021, report 2022-2026, and show the per-trade tail so the risk
is priced rather than argued about.
"""
import warnings; warnings.filterwarnings("ignore")
import collections
import pandas as pd
import v13_engine as E
import v13_target as T

CAP = T.CAP0
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08, spread=0.00105,
            capture=True)
BRAKE = {"50/25": ((-0.006, 0.50), (-0.012, 0.25)),
         "45/22": ((-0.006, 0.45), (-0.012, 0.22))}
WIDTHS = [("SL 4%", 0.04, False), ("SL 6%", 0.06, False), ("SL 8%", 0.08, False),
          ("SL 10%", 0.10, False), ("no SL", 0.04, True)]

print("stop width is a module global in v13_engine; patching it changes execution only")
print("brake  stop    13yr   2014-21  2022-26     MDD   worstYr  stop%  worst1   p5     win%  /day")
rows = []
for bname, brake in BRAKE.items():
    for tag, slo, nosl in WIDTHS:
        E.SLO = slo
        y = T.run(**dict(base, brake=brake, nosl=nosl))
        yr = y["yearly"]; ks = sorted(yr)
        v = [yr[k] / CAP * 100 for k in ks]

        def avg(a, b):
            s = [x for k, x in zip(ks, v) if a <= k <= b]
            return sum(s) / len(s)
        tr = pd.DataFrame([dict(zip("date code dir notional gross reason entry exit".split(), t))
                           for t in y["trades"]])
        q = tr["gross"] * 100
        # stop share, language-neutral: everything that is neither the force
        # close nor the take-profit is a stop leg, including the price-limit bound ones.
        stopped = ((~tr["reason"].str.startswith("13:25"))
                   & (~tr["reason"].str.contains("TP"))).mean() * 100
        print("%-6s %-7s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+7.1f%% %5.1f%% %+6.2f%% %+6.2f%% %5.1f%% %5.1f"
              % (bname, tag, sum(v) / len(v), avg(2014, 2021), avg(2022, 2026), y["mdd"],
                 min(v), stopped, q.min(), q.quantile(.05),
                 (q > 0).mean() * 100, y["per_day"]), flush=True)
        rows.append(dict(brake=bname, tag=tag, mdd=y["mdd"], recent=avg(2022, 2026),
                         worst1=q.min(), stopped=stopped))
E.SLO = 0.04
pd.DataFrame(rows).to_csv("_sl_width.csv", index=False)
print("\nsaved _sl_width.csv")
