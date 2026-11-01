"""gap_max 0.04 is the only gap threshold whose MDD does not move across exposures
(1.00/1.25/1.50/1.75 all -3.65 pct) or across the entry-cost assumption. That makes it
the parameter to ship rather than 0.06, which was picked at 1.25x and breaks at 1.75x.
Full confirmation battery on the 1.75x / 0.04 candidate.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
TRAIN = range(2014, 2022)
TEST = range(2022, 2027)
LIVE = ((-0.006, 0.30), (-0.012, 0.12))
CAND = dict(brake=LIVE, liq=0.10, gap_max=0.04, exposure=1.75, spread=0.0)


def ev(**cfg):
    r = T.run(**cfg)
    y = r["yearly"]
    allr = [y[k] / CAP0 * 100 for k in sorted(y)]
    tr = [y[k] / CAP0 * 100 for k in sorted(y) if k in TRAIN]
    te = [y[k] / CAP0 * 100 for k in sorted(y) if k in TEST]
    return r, np.mean(allr), np.mean(tr), np.mean(te), min(allr)


print("=== gap neighbourhood at exposure 1.75, fine ===")
for gm in (0.025, 0.03, 0.035, 0.04, 0.045, 0.05):
    r, al, tr, te, wo = ev(**dict(CAND, gap_max=gm))
    print("  gap %-5s MDD %+6.2f%%  13yr %+7.1f%%  train %+7.1f%%  test %+7.1f%%  worst yr %+7.1f%%  筆/日 %4.1f"
          % (gm, r["mdd"], al, tr, te, wo, r["per_day"]))
print()
print("=== exposure neighbourhood at gap_max=0.04 ===")
for ex in (1.0, 1.25, 1.5, 1.6, 1.75, 1.9, 2.0):
    r, al, tr, te, wo = ev(**dict(CAND, exposure=ex))
    print("  exposure %.2f  MDD %+6.2f%%  13yr %+7.1f%%  train %+7.1f%%  test %+7.1f%%  worst yr %+7.1f%%  融資 %.0f 萬"
          % (ex, r["mdd"], al, tr, te, wo, ex * 450))
print()
print("=== brake sensitivity ===")
for mult in (0.5, 0.75, 1.0, 1.5, 2.0):
    bk = ((LIVE[0][0] * mult, LIVE[0][1]), (LIVE[1][0] * mult, LIVE[1][1]))
    r, al, tr, te, wo = ev(**dict(CAND, brake=bk))
    print("  thresholds x%-4.2f  MDD %+6.2f%%  13yr %+7.1f%%  煞車 %4.1f%%" % (mult, r["mdd"], al, r["brake_pct"]))
print()
print("=== liquidity floor sensitivity ===")
for lq in (0.05, 0.10, 0.15, 0.20):
    r, al, tr, te, wo = ev(**dict(CAND, liq=lq))
    print("  liq %.2f  MDD %+6.2f%%  13yr %+7.1f%%  筆/日 %4.1f  參與p90 %.1f%%" % (lq, r["mdd"], al, r["per_day"], r["part90"]))
print()
r, al, tr, te, wo = ev(**CAND)
y = r["yearly"]
print("=== CANDIDATE: exposure 1.75, gap_max 0.04, entry at auction price ===")
print("  13 年年均 %+.1f%%   部位MDD %+.2f%%   最差年 %+.1f%%   2014-21 %+.1f%%   2022-26 %+.1f%%"
      % (al, r["mdd"], wo, tr, te))
print("  筆/日 %.1f  平均曝險 %.0f%%  最大曝險 %.0f%%  參與p90 %.1f%%  煞車日 %.1f%%"
      % (r["per_day"], r["expo"], r["expo_max"], r["part90"], r["brake_pct"]))
print("  逐年：", " ".join("%d %+.0f%%" % (k, y[k] / CAP0 * 100) for k in sorted(y)))
print()
for sp, lab in ((T.SPREAD / 2, "1/4 價差"), (T.SPREAD, "半價差")):
    r2, al2, tr2, te2, wo2 = ev(**dict(CAND, spread=sp))
    print("  paying %s: 13yr %+.1f%%  MDD %+.2f%%  worst %+.1f%%  test %+.1f%%" % (lab, al2, r2["mdd"], wo2, te2))
