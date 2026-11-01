# -*- coding: utf-8 -*-
r"""The two identified levers, together.

Nothing else about the book changes. Two things are turned on one at a time and
then both:

  nozt    : do not stop at the price limit (measured ceiling for the limit-lock
            rule; v17_r2.py shows a submittable limit order recovers it).
  spread0 : pay no closing half-spread on entry. That is the auction assumption
            - the auction has one price, so there is no spread to pay. Whether
            the pre-open indicative price actually updates is being measured
            2026-11-02; until then this is a conditional, not a result.

Both are measured on the shipped configuration: exposure 1.00x, the broker's
absolute 4.5M line, brake 50/25, profits withdrawn so every year is a fresh
4.5M book.
"""
import warnings; warnings.filterwarnings("ignore")
import v13_target as T

brake = ((-0.006, 0.50), (-0.012, 0.25))
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, brake=brake, cost_mode="measured", gap_max_long=0.08)
CASES = [("A 現行（吃半價差、觸價限停損）", dict(nozt=False, spread=0.00105)),
         ("B 只放開價限停損", dict(nozt=True, spread=0.00105)),
         ("C 只不吃價差（競價假設）", dict(nozt=False, spread=0.0)),
         ("D 兩個都要", dict(nozt=True, spread=0.0))]
res = {}
for tag, kw in CASES:
    res[tag] = T.run(**dict(base, **kw))
    print("done:", tag, flush=True)

def rows(y):
    yr = y["yearly"]; ks = sorted(yr)
    return ks, [yr[k] / T.CAP0 * 100 for k in ks]

ks, ref = rows(res[CASES[0][0]])
print("\n年  " + "".join("  %-10s" % t.split()[0] for t, _ in CASES))
for i, k in enumerate(ks):
    print("%d " % k + "".join("  %+9.1f " % rows(res[t])[1][i] for t, _ in CASES))
print()
for t, _ in CASES:
    _, v = rows(res[t])
    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    print("%-34s 13yr %+.1f%%  2014-21 %+.1f%%  2022-26 %+.1f%%  MDD %.2f%%  最差 %+.1f%%"
          % (t, sum(v) / len(v), avg(2014, 2021), avg(2022, 2026), res[t]["mdd"], min(v)))
