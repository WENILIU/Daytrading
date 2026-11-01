# -*- coding: utf-8 -*-
r"""Is the ordinary 4 pct stop earning its keep?

The stop-loss is the one rule the whole book is built around, and the number
that used to justify relaxing it (+21 pct) turned out to be mostly the ordinary
stops wearing a limit-touch label. Now that the labels are correct, measure the
question directly: keep every stop (A/B), keep only the non-limit stops (nozt),
or keep none at all (nosl) and let the 13:25 force close be the exit.

nosl is not free. A stop that is never hit is a stop that was doing nothing;
a stop that is hit and then held is a real loss carried to the close. The only
honest way to know which of those dominates is to price both.

B is re-run here as a regression: adding the nosl parameter must not move it.
"""
import warnings; warnings.filterwarnings("ignore")
import v13_target as T

brake = ((-0.006, 0.50), (-0.012, 0.25))
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, brake=brake, cost_mode="measured", gap_max_long=0.08)
CASES = [("B 只放開價限停損（回歸檢查）", dict(nozt=True, nosl=False, spread=0.00105)),
         ("E 完全不設停損（吃半價差）", dict(nozt=False, nosl=True, spread=0.00105)),
         ("F 完全不設停損＋不吃價差", dict(nozt=False, nosl=True, spread=0.0))]
res = {}
for tag, kw in CASES:
    res[tag] = T.run(**dict(base, **kw))
    print("done:", tag, flush=True)

def rows(y):
    yr = y["yearly"]; ks = sorted(yr)
    return ks, [yr[k] / T.CAP0 * 100 for k in ks]

ks = rows(res[CASES[0][0]])[0]
print("\n年  " + "".join("  %-14s" % t.split()[0] for t, _ in CASES))
for i, k in enumerate(ks):
    print("%d " % k + "".join("  %+13.1f " % rows(res[t])[1][i] for t, _ in CASES))
print()
for t, _ in CASES:
    _, v = rows(res[t])
    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    print("%-30s 13yr %+.1f%%  2014-21 %+.1f%%  2022-26 %+.1f%%  MDD %.2f%%  最差 %+.1f%%  筆/日 %.1f"
          % (t, sum(v) / len(v), avg(2014, 2021), avg(2022, 2026), res[t]["mdd"], min(v),
             res[t]["per_day"]))
