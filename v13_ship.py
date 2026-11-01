"""Ship 1.90, not 1.75. Participation p90 is 6.6 pct at 1.00x and 7.2 pct at 2.00x, so
the ceiling does not size the orders (the per-name liquidity cap does) - it only adds
names. Same drawdown, same fill assumptions, and it clears 100 pct on the 13-year
average instead of 98. Full detail for the docs."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
TRAIN = range(2014, 2022)
TEST = range(2022, 2027)
LIVE = ((-0.006, 0.30), (-0.012, 0.12))
CAND = dict(brake=LIVE, liq=0.10, gap_max=0.04, gap_max_long=0.08, exposure=1.90, spread=0.0)


def ev(**cfg):
    r = T.run(**cfg)
    y = r["yearly"]
    allr = {k: y[k] / CAP0 * 100 for k in sorted(y)}
    return r, allr, np.mean(list(allr.values())), np.mean([v for k, v in allr.items() if k in TRAIN]), \
        np.mean([v for k, v in allr.items() if k in TEST]), min(allr.values())


r, yr, al, tr, te, wo = ev(**CAND)
print("=== v15 shipped: SHORT<=4 pct, LONG<=8 pct, exposure 1.90 ===")
print("  13 年年均 %+.1f%%  部位MDD %+.2f%%  最差年 %+.1f%%  2014-21 %+.1f%%  2022-26 %+.1f%%" % (al, r["mdd"], wo, tr, te))
print("  筆/日 %.1f  平均曝險 %.0f%%  最大曝險 %.0f%%  參與p90 %.1f%%  煞車日 %.1f%%  總獲利 %.0f 萬"
      % (r["per_day"], r["expo"], r["expo_max"], r["part90"], r["brake_pct"], r["withdrawn"] / 1e4))
print("  逐年：", " ".join("%d %+.0f" % (k, v) for k, v in yr.items()))
print("  負年數：%d / 13" % sum(1 for v in yr.values() if v < 0))
n = r["dir_n"]; dy = r["dir_y"]; tot = sum(dy.values())
print("  SHORT %d 筆 %+.0f 萬 (%.1f%%)   LONG %d 筆 %+.0f 萬 (%.1f%%)"
      % (n["SHORT"], dy["SHORT"] / 1e4, dy["SHORT"] / tot * 100, n["LONG"], dy["LONG"] / 1e4, dy["LONG"] / tot * 100))
print()
for sp, lab in ((T.SPREAD / 2, "1/4 價差"), (T.SPREAD, "半價差")):
    r2, y2, al2, tr2, te2, wo2 = ev(**dict(CAND, spread=sp))
    print("  %s: 13yr %+.1f%%  MDD %+.2f%%  worst %+.1f%%  test %+.1f%%" % (lab, al2, r2["mdd"], wo2, te2))
print()
print("=== the fallback ladder, if the credit line cannot be obtained ===")
for ex in (1.0, 1.5, 1.75, 1.9):
    r3, y3, al3, tr3, te3, wo3 = ev(**dict(CAND, exposure=ex))
    print("  %.2fx  融資 %4.0f 萬  13yr %+7.1f%%  test %+7.1f%%  MDD %+6.2f%%  worst %+6.1f%%  筆/日 %4.1f"
          % (ex, ex * 450, al3, te3, r3["mdd"], wo3, r3["per_day"]))
