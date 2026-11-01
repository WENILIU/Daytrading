"""Confirm the chosen configuration is a plateau, not a peak.

gap_max=0.06 beat 0.07 in the grid. One value beating its neighbour is what an
overfit parameter looks like, so sweep the whole neighbourhood, sweep the brake,
and print the year-by-year book for the two configurations that would actually be
traded: the one with a 1.25x deployment ceiling, and the zero-margin one.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
TRAIN = range(2014, 2022)
TEST = range(2022, 2027)
LIVE = ((-0.006, 0.30), (-0.012, 0.12))


def ev(**cfg):
    r = T.run(**cfg)
    y = r["yearly"]
    tr = [y[k] / CAP0 * 100 for k in sorted(y) if k in TRAIN]
    te = [y[k] / CAP0 * 100 for k in sorted(y) if k in TEST]
    return r, np.mean(tr), np.mean(te), min(te)


CH = dict(brake=LIVE, liq=0.10, gap_max=0.06, exposure=1.25, spread=0.0)

print("=== gap filter neighbourhood (liq 0.10, exposure 1.25, limit-order entry) ===")
print("  %8s %8s %8s %8s %8s %7s" % ("gap_max", "MDD%", "train%", "test%", "worst yr", "筆/日"))
for gm in (0.04, 0.05, 0.06, 0.07, 0.08, 0.10, None):
    r, tr, te, tw = ev(**dict(CH, gap_max=gm))
    print("  %8s %+8.2f %+8.1f %+8.1f %+8.1f %7.1f" %
          (gm if gm else "none", r["mdd"], tr, te, tw, r["per_day"]))
print()
print("=== exposure neighbourhood at gap_max=0.06 ===")
for ex in (1.0, 1.1, 1.25, 1.4, 1.5):
    r, tr, te, tw = ev(**dict(CH, exposure=ex))
    print("  exposure %.2f  MDD %+6.2f%%  train %+7.1f%%  test %+7.1f%%  worst %+7.1f%%  max-deploy %.0f%%"
          % (ex, r["mdd"], tr, te, tw, r["expo_max"]))
print()
print("=== brake robustness on the chosen configuration ===")
for mult in (0.5, 0.75, 1.0, 1.5, 2.0):
    bk = ((LIVE[0][0] * mult, LIVE[0][1]), (LIVE[1][0] * mult, LIVE[1][1]))
    r, tr, te, tw = ev(**dict(CH, brake=bk))
    print("  thresholds x%-4.2f  MDD %+6.2f%%  train %+7.1f%%  test %+7.1f%%  煞車 %4.1f%%"
          % (mult, r["mdd"], tr, te, r["brake_pct"]))
for s1, s2 in ((0.20, 0.08), (0.30, 0.12), (0.40, 0.20)):
    bk = ((LIVE[0][0], s1), (LIVE[1][0], s2))
    r, tr, te, tw = ev(**dict(CH, brake=bk))
    print("  floors %2.0f%%/%2.0f%%  MDD %+6.2f%%  train %+7.1f%%  test %+7.1f%%" %
          (s1 * 100, s2 * 100, r["mdd"], tr, te))
print()
for lbl, cfg in (("v14  ceiling 1.25x (需融資至 563 萬)", CH),
                 ("zero-margin  ceiling 1.00x", dict(CH, exposure=1.0)),
                 ("v14 but paying the half-spread", dict(CH, spread=T.SPREAD))):
    r, tr, te, tw = ev(**cfg)
    y = r["yearly"]
    print("=== %s ===" % lbl)
    print("  部位MDD %+.2f%%  全期年均 %+.1f%%  train(14-21) %+.1f%%  test(22-26) %+.1f%%  最差年 %+.1f%%"
          % (r["mdd"], np.mean([y[k] / CAP0 * 100 for k in sorted(y)]), tr, te, tw))
    print("  筆/日 %.1f  煞車日 %.1f%%  平均曝險 %.0f%%  最大曝險 %.0f%%  參與p90 %.1f%%"
          % (r["per_day"], r["brake_pct"], r["expo"], r["expo_max"], r["part90"]))
    print("  逐年：", " ".join("%d %+.0f%%" % (k, y[k] / CAP0 * 100) for k in sorted(y)))
    print()
