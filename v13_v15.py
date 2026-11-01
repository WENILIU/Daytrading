"""Direction-aware caps. Rationale is not curve-fitting: SHORT is capped where the
limit-stop starts to bite (the 2026 stop-out rate is 40 pct, and a 4 pct gap keeps the
price limit far from the stop), LONG is capped where the measured entry cost turns bad
(ENTRY_COST: LONG >=10 pct gap costs +0.72 pct of notional). Confirm both caps hold."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
TRAIN = range(2014, 2022)
TEST = range(2022, 2027)
LIVE = ((-0.006, 0.30), (-0.012, 0.12))
CAND = dict(brake=LIVE, liq=0.10, gap_max=0.04, gap_max_long=0.08, exposure=1.75, spread=0.0)


def ev(**cfg):
    r = T.run(**cfg)
    y = r["yearly"]
    allr = [y[k] / CAP0 * 100 for k in sorted(y)]
    tr = [y[k] / CAP0 * 100 for k in sorted(y) if k in TRAIN]
    te = [y[k] / CAP0 * 100 for k in sorted(y) if k in TEST]
    return r, np.mean(allr), np.mean(tr), np.mean(te), min(allr)


print("=== SHORT cap fine sweep (LONG cap 0.08, exposure 1.75) ===")
for sc in (0.03, 0.035, 0.04, 0.045, 0.05, 0.06):
    r, al, tr, te, wo = ev(**dict(CAND, gap_max=sc))
    print("  SHORT<=%-5s MDD %+6.2f%%  13yr %+7.1f%%  train %+7.1f%%  test %+7.1f%%  worst yr %+7.1f%%  筆/日 %4.1f"
          % (sc, r["mdd"], al, tr, te, wo, r["per_day"]))
print()
print("=== LONG cap (SHORT cap 0.04) ===")
for lc in (0.06, 0.07, 0.08, 0.10, None):
    r, al, tr, te, wo = ev(**dict(CAND, gap_max_long=lc))
    print("  LONG<=%-5s MDD %+6.2f%%  13yr %+7.1f%%  test %+7.1f%%  worst yr %+7.1f%%  L %5d 筆"
          % (lc if lc else "none", r["mdd"], al, te, wo, r["dir_n"]["LONG"]))
print()
print("=== exposure neighbourhood (SHORT<=0.04, LONG<=0.08) ===")
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
r, al, tr, te, wo = ev(**CAND)
y = r["yearly"]
print("=== CANDIDATE v15: SHORT<=4 pct, LONG<=8 pct, exposure 1.75, 競價價進場 ===")
print("  13 年年均 %+.1f%%   部位MDD %+.2f%%   最差年 %+.1f%%   2014-21 %+.1f%%   2022-26 %+.1f%%"
      % (al, r["mdd"], wo, tr, te))
print("  筆/日 %.1f  平均曝險 %.0f%%  最大曝險 %.0f%%  參與p90 %.1f%%  煞車日 %.1f%%  總獲利 %.0f 萬"
      % (r["per_day"], r["expo"], r["expo_max"], r["part90"], r["brake_pct"], r["withdrawn"] / 1e4))
print("  逐年：", " ".join("%d %+.0f%%" % (k, y[k] / CAP0 * 100) for k in sorted(y)))
print()
for sp, lab in ((T.SPREAD / 2, "1/4 價差"), (T.SPREAD, "半價差")):
    r2, al2, tr2, te2, wo2 = ev(**dict(CAND, spread=sp))
    print("  paying %s: 13yr %+.1f%%  MDD %+.2f%%  worst %+.1f%%  test %+.1f%%" % (lab, al2, r2["mdd"], wo2, te2))
