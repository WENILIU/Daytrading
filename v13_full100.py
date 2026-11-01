"""Is there a configuration that clears 100 pct on the FULL 13 years, not just the
recent window? v13_target5 has one row that suggests it (exposure 1.75, gap_max 0.07).
One row off a grid is not a result, so repeat the whole confirmation battery on it:
gap neighbourhood, exposure neighbourhood, brake sensitivity, and the year-by-year book.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
TRAIN = range(2014, 2022)
TEST = range(2022, 2027)
LIVE = ((-0.006, 0.30), (-0.012, 0.12))
CAND = dict(brake=LIVE, liq=0.10, gap_max=0.07, exposure=1.75, spread=0.0)


def ev(**cfg):
    r = T.run(**cfg)
    y = r["yearly"]
    allr = [y[k] / CAP0 * 100 for k in sorted(y)]
    tr = [y[k] / CAP0 * 100 for k in sorted(y) if k in TRAIN]
    te = [y[k] / CAP0 * 100 for k in sorted(y) if k in TEST]
    return r, np.mean(allr), np.mean(tr), np.mean(te), min(allr)


print("=== gap neighbourhood at exposure 1.75 ===")
print("  %8s %8s %9s %8s %8s %8s %7s" % ("gap_max", "MDD%", "13yr avg", "train", "test", "worst yr", "筆/日"))
for gm in (0.04, 0.05, 0.06, 0.07, 0.08, None):
    r, al, tr, te, wo = ev(**dict(CAND, gap_max=gm))
    print("  %8s %+8.2f %+9.1f %+8.1f %+8.1f %+8.1f %7.1f" %
          (gm if gm else "none", r["mdd"], al, tr, te, wo, r["per_day"]))
print()
print("=== exposure neighbourhood at gap_max=0.07 ===")
for ex in (1.25, 1.5, 1.6, 1.75, 1.9, 2.0):
    r, al, tr, te, wo = ev(**dict(CAND, exposure=ex))
    print("  exposure %.2f  MDD %+6.2f%%  13yr %+7.1f%%  train %+7.1f%%  test %+7.1f%%  worst yr %+7.1f%%  融資 %.0f 萬"
          % (ex, r["mdd"], al, tr, te, wo, ex * 450))
print()
print("=== brake sensitivity on the candidate ===")
for mult in (0.5, 0.75, 1.0, 1.5, 2.0):
    bk = ((LIVE[0][0] * mult, LIVE[0][1]), (LIVE[1][0] * mult, LIVE[1][1]))
    r, al, tr, te, wo = ev(**dict(CAND, brake=bk))
    print("  thresholds x%-4.2f  MDD %+6.2f%%  13yr %+7.1f%%  煞車 %4.1f%%" % (mult, r["mdd"], al, r["brake_pct"]))
print()
r, al, tr, te, wo = ev(**CAND)
y = r["yearly"]
print("=== candidate in full: exposure 1.75, gap_max 0.07, limit-order entry ===")
print("  13 年年均 %+.1f%%   部位MDD %+.2f%%   最差年 %+.1f%%   2014-21 %+.1f%%   2022-26 %+.1f%%"
      % (al, r["mdd"], wo, tr, te))
print("  筆/日 %.1f  平均曝險 %.0f%%  最大曝險 %.0f%%  參與p90 %.1f%%  煞車日 %.1f%%"
      % (r["per_day"], r["expo"], r["expo_max"], r["part90"], r["brake_pct"]))
print("  逐年：", " ".join("%d %+.0f%%" % (k, y[k] / CAP0 * 100) for k in sorted(y)))
print()
print("  same candidate but paying the half spread:")
r2, al2, tr2, te2, wo2 = ev(**dict(CAND, spread=T.SPREAD))
print("    13yr %+.1f%%  MDD %+.2f%%  worst %+.1f%%" % (al2, r2["mdd"], wo2))
