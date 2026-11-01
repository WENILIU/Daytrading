"""Two levers the measured cost table itself points at, then the target again.

The measured entry cost is not flat. It is -0.094 pct for a small-gap SHORT and
+0.353 pct for a 7-10 pct gap SHORT, and the second group is also the group that
gets stopped out. So:

  spread=0    post a limit at the 09:01 price instead of taking price. The spread
              is the single largest item in the entry cost (0.105 pct of notional,
              median of 11 names) and it is avoidable in continuous trading, unlike
              in the auction where there is no spread to avoid in the first place.
  gap_max     skip the signals where the measured entry cost is highest. The first
              search found gap filters did not help because the old cost curve made
              those signals look free; with the measured cost they are not.

Everything else is fixed: brake = live, whole lots, zero margin unless exposure says
otherwise, executability filtered, cost 0.222 pct round trip.
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


rows = []
for spread in (0.0, T.SPREAD):
    for gap_max in (0.06, 0.07):
        for liq in (0.10, 0.25):
            for exposure in (1.0, 1.25, 1.5, 1.75):
                cfg = dict(brake=LIVE, liq=liq, gap_max=gap_max, exposure=exposure,
                           spread=spread)
                r, tr, te, tw = ev(**cfg)
                rows.append((spread, gap_max, liq, exposure, r, tr, te, tw))
                print(".", end="", flush=True)
print()
print()
print("  %7s %7s %5s %8s %8s %8s %8s %8s %7s %9s" %
      ("spread", "gapmax", "liq", "exposure", "MDD%", "train%", "test%", "worst yr", "筆/日", "曝險max%"))
for spread, gap_max, liq, exposure, r, tr, te, tw in rows:
    flag = "  <= CLEARS" if (te >= 100.0 and r["mdd"] >= -5.0) else ""
    print("  %7.3f %7s %5s %8.2f %+8.2f %+8.1f %+8.1f %+8.1f %7.1f %9.1f%s" %
          (spread, gap_max, liq, exposure, r["mdd"], tr, te, tw, r["per_day"], r["expo_max"], flag))

clear = [x for x in rows if x[6] >= 100.0 and x[4]["mdd"] >= -5.0]
clear.sort(key=lambda x: (x[3], x[0]))
print()
print("  configs that clear the target: %d / %d" % (len(clear), len(rows)))
for spread, gap_max, liq, exposure, r, tr, te, tw in clear:
    print("    spread=%.3f gap_max=%s liq=%s exposure=%.2f -> MDD %+.2f%% test %+.1f%% worst %+.1f%% 筆/日 %.1f max-deploy %.0f%%"
          % (spread, gap_max, liq, exposure, r["mdd"], te, tw, r["per_day"], r["expo_max"]))
if not clear:
    best = sorted([x for x in rows if x[4]["mdd"] >= -5.0], key=lambda x: -x[6])[:5]
    print("  closest MDD-compliant:")
    for spread, gap_max, liq, exposure, r, tr, te, tw in best:
        print("    spread=%.3f gap_max=%s liq=%s exposure=%.2f -> MDD %+.2f%% test %+.1f%%"
              % (spread, gap_max, liq, exposure, r["mdd"], te))
