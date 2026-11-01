# -*- coding: utf-8 -*-
r"""Re-measure the nozt upper bound after the label fix.

v13_target.run(nozt=True) rewrites every exit whose reason starts with 停損(觸.
Before the fix that bucket was 3,934 trades and was mostly ordinary 4% stops, so
the +21 pct it produced was mostly "let the stop-loss run to the close", not
"relax the price-limit lock". Same call, corrected bucket.
"""
import warnings; warnings.filterwarnings("ignore")
import v13_target as T

brake = ((-0.006, 0.50), (-0.012, 0.25))
kw = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
          order_cap=30, brake=brake, cost_mode="measured", spread=0.00105,
          gap_max_long=0.08)
for tag, nozt in (("現行（觸價限即停損）", False), ("nozt（觸價限改結收盤）", True)):
    y = T.run(**dict(kw, nozt=nozt))
    yr = y["yearly"]
    ks = sorted(yr)
    rets = [yr[k] / T.CAP0 * 100 for k in ks]
    def avg(a, b):
        s = [r for k, r in zip(ks, rets) if a <= k <= b]
        return sum(s) / len(s)
    print("%-24s 13yr %+.1f%%  MDD %.2f%%  2014-21 %+.1f%%  2022-26 %+.1f%%  最差 %+.1f%%"
          % (tag, sum(rets) / len(rets), y["mdd"] * 100, avg(2014, 2021), avg(2022, 2026), min(rets)), flush=True)
