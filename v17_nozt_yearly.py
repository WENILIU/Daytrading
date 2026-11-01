# -*- coding: utf-8 -*-
r"""Yearly table for the corrected limit-lock upper bound.

nozt rewrites every exit labelled 停損(觸. After the label fix that bucket is the
583 genuine price-limit-bound stops and nothing else, so this is the honest
ceiling for "do not stop at the price limit". R2 (rest a limit order back from
the limit, measured on 1-minute bars in v17_r2.py) recovers most of it.
"""
import warnings; warnings.filterwarnings("ignore")
import v13_target as T

brake = ((-0.006, 0.50), (-0.012, 0.25))
kw = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
          order_cap=30, brake=brake, cost_mode="measured", spread=0.00105,
          gap_max_long=0.08)
out = {}
for tag, nozt in (("ship", False), ("nozt", True)):
    out[tag] = T.run(**dict(kw, nozt=nozt))

def table(y):
    yr = y["yearly"]; ks = sorted(yr)
    return ks, [yr[k] / T.CAP0 * 100 for k in ks]

ks, a = table(out["ship"]); _, b = table(out["nozt"])
print("年      現行%     上界%     差pp   筆數")
for i, k in enumerate(ks):
    print("%d   %+7.1f  %+7.1f  %+6.1f  %5d" % (k, a[i], b[i], b[i] - a[i], out["ship"]["per_day"].get(k, 0) if isinstance(out["ship"].get("per_day"), dict) else 0))
def avg(v, lo, hi):
    s = [x for k, x in zip(ks, v) if lo <= k <= hi]
    return sum(s) / len(s)
print("\n13yr 現行 %+.1f%%  上界 %+.1f%%" % (sum(a) / len(a), sum(b) / len(b)))
print("2014-2021 現行 %+.1f%%  上界 %+.1f%%" % (avg(a, 2014, 2021), avg(b, 2014, 2021)))
print("2022-2026 現行 %+.1f%%  上界 %+.1f%%" % (avg(a, 2022, 2026), avg(b, 2022, 2026)))
print("MDD 現行 %.2f%%  上界 %.2f%%" % (out["ship"]["mdd"], out["nozt"]["mdd"]))
print("最差年 現行 %+.1f%%  上界 %+.1f%%" % (min(a), min(b)))
