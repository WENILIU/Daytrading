# -*- coding: utf-8 -*-
r"""User's rule: stop ONLY the orders that would run into a price limit; let every
other order ride the mean-reversion to 13:25.

Implementation = replace the stop level. exit_of_legal uses slp = min(4% stop,
limit-tick). The user wants the 4% component GONE and only the limit-tick stop kept:
  SHORT stop = lu - tick (cover just below limit-up, a price that IS traded -> avoids
  the -3.149% pin), LONG stop = ld + tick. A trade that never reaches the limit has
  no stop and settles at the 13:25 close. TP unchanged.

exit_of_legal is only called in run()'s settlement; kT/sizing read the trained p from
the pickle, not this, so patching it changes only the exit. We compare three books on
identical sizing (B-arm best: gap .04 / oc 20 / liq .10 / brake 50-25 / measured cost):
  A) pure stop (exit_of_legal, nosl=False)        -> the +45.2 / -4.09 baseline
  B) no stop at all (nosl=True)                   -> the +81.8 / -4.80 frontier
  C) stop only at the limit (this file)           -> what the user asked for
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T
from v13_engine import snap_price

CAP = T.CAP0
_orig = T.exit_of_legal

def exit_limit_only(direction, entry, hi, lo, cl, lu, ld, tk, tp):
    if direction == "SHORT":
        tpp = snap_price(entry * (1 - tp))
        if lo <= tpp:
            return tpp, tpp, tpp, "停利 TP", (entry - tpp) / entry
        slp = round(lu - tk, 2)
        if slp > entry and hi >= slp:            # ran up to the limit -> cover before it pins
            return slp, slp, tpp, "停損(觸漲停上限)", -(slp - entry) / entry
        return cl, slp, tpp, "13:25 強制平倉", (entry - cl) / entry
    tpp = snap_price(entry * (1 + tp))
    if hi >= tpp:
        return tpp, tpp, tpp, "停利 TP", (tpp - entry) / entry
    slp = round(ld + tk, 2)
    if slp < entry and lo <= slp:                # ran down to the limit -> exit before it pins
        return slp, slp, tpp, "停損(觸跌停下限)", -(entry - slp) / entry
    return cl, slp, tpp, "13:25 強制平倉", (cl - entry) / entry

base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00,
            gap_max_long=0.08, spread=0.00105, cost_mode="measured",
            brake=((-0.008, .50), (-0.016, .25)))

def summarize(tag, y):
    yr = y["yearly"]; ks = sorted(yr); v = [yr[k] / CAP * 100 for k in ks]
    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]; return sum(s) / len(s)
    allr, old, recent, m = sum(v)/len(v), avg(2014,2021), avg(2022,2026), y["mdd"]
    print("%-34s 13yr %+6.1f%%  2014-21 %+7.1f%%  2022-26 %+7.1f%%  MDD %6.2f%%  比值 %5.1f  筆/日 %4.1f"
          % (tag, allr, old, recent, m, recent/abs(m), y["per_day"]), flush=True)
    return dict(tag=tag, all=allr, old=old, recent=recent, mdd=m, ratio=recent/abs(m), per_day=y["per_day"])

rows = []
print("%-34s %14s %14s %14s %8s %7s %7s" % ("book","13yr","2014-21","2022-26","MDD","ratio","per_day"), flush=True)
for cap, oc in [(0.040, 20), (0.030, 20)]:
    # A) pure stop
    T.exit_of_legal = _orig
    rows.append(summarize("A 純停損 g%.3f oc%d" % (cap, oc), T.run(**dict(base, gap_max=cap, order_cap=oc, nosl=False))))
    # B) no stop at all
    rows.append(summarize("B 完全不設停損 g%.3f oc%d" % (cap, oc), T.run(**dict(base, gap_max=cap, order_cap=oc, nosl=True))))
    # C) stop only at the limit (the user's rule)
    T.exit_of_legal = exit_limit_only
    rows.append(summarize("C 只停會觸板的單 g%.3f oc%d" % (cap, oc), T.run(**dict(base, gap_max=cap, order_cap=oc, nosl=False))))
    T.exit_of_legal = _orig
pd.DataFrame(rows).to_csv("_limit_only.csv", index=False)
print("saved _limit_only.csv", flush=True)
