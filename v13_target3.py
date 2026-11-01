"""Two questions the first search left open.

1. What is the smallest amount of margin that clears 100 pct a year on the
   validation window? exposure=1.0 tops out near 94 pct, so the answer decides
   whether the target needs borrowing at all.
2. Is the result load-bearing on the brake, or an artefact of its exact numbers?
   The first search found only the live brake keeps MDD inside -5 pct, which means
   the brake - not the signal - is what makes 2x and 3x exposure safe. If MDD moves
   a lot under a small change to the brake, that is fragile and must be said.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
TRAIN = range(2014, 2022)
TEST = range(2022, 2027)
LIVE = ((-0.006, 0.30), (-0.012, 0.12))


def ev(cfg):
    r = T.run(**cfg)
    y = r["yearly"]
    tr = [y[k] / CAP0 * 100 for k in sorted(y) if k in TRAIN]
    te = [y[k] / CAP0 * 100 for k in sorted(y) if k in TEST]
    return r, np.mean(tr), np.mean(te), min(te)


print("=== 1. minimum margin that clears the target (brake = live, slip 1.00) ===")
print("  %8s %6s %8s %8s %8s %8s %8s %7s" %
      ("exposure", "liq", "gapmax", "MDD%", "train%", "test%", "worst yr", "筆/日"))
best = []
for exposure in (1.0, 1.25, 1.5, 1.75, 2.0):
    for liq in (0.10, 0.25):
        for gap_max in (None, 0.10, 0.07):
            cfg = dict(brake=LIVE, liq=liq, slip_scale=1.0, gap_max=gap_max, exposure=exposure)
            r, tr, te, tw = ev(cfg)
            flag = "  <= clears" if (te >= 100.0 and r["mdd"] >= -5.0) else ""
            print("  %8.2f %6s %8s %+8.2f %+8.1f %+8.1f %+8.1f %7.1f%s" %
                  (exposure, liq, gap_max if gap_max else "-", r["mdd"], tr, te, tw,
                   r["per_day"], flag))
            best.append((exposure, liq, gap_max, r, tr, te, tw))
print()
clear = [b for b in best if b[5] >= 100.0 and b[3]["mdd"] >= -5.0]
clear.sort(key=lambda b: b[0])
if clear:
    e, l, g, r, tr, te, tw = clear[0]
    print("  smallest exposure that clears: %.2f (liq=%s gap_max=%s) -> test %+.1f%%, MDD %+.2f%%"
          % (e, l, g, te, r["mdd"]))
    print("  zero-margin configs that clear: %d" % len([b for b in clear if b[0] <= 1.0]))

print()
print("=== 2. brake sensitivity. Config: exposure=2.0, liq=0.10, gap_max=0.10 ===")
BASE = dict(liq=0.10, slip_scale=1.0, gap_max=0.10, exposure=2.0)
for mult in (0.5, 0.75, 1.0, 1.5, 2.0, 3.0):
    bk = ((LIVE[0][0] * mult, LIVE[0][1]), (LIVE[1][0] * mult, LIVE[1][1]))
    r, tr, te, tw = ev(dict(BASE, brake=bk))
    print("  thresholds x%-4.2f (%+.1f%%/%+.1f%% -> %2.0f%%/%2.0f%%)  MDD %+6.2f%%  train %+7.1f%%  test %+7.1f%%  煞車 %4.1f%%"
          % (mult, LIVE[0][0] * mult * 100, LIVE[1][0] * mult * 100,
             LIVE[0][1] * 100, LIVE[1][1] * 100, r["mdd"], tr, te, r["brake_pct"]))
print()
print("=== 3. same config with the size floors changed (not the thresholds) ===")
for s1, s2 in ((0.20, 0.08), (0.30, 0.12), (0.40, 0.20), (0.60, 0.35)):
    bk = ((LIVE[0][0], s1), (LIVE[1][0], s2))
    r, tr, te, tw = ev(dict(BASE, brake=bk))
    print("  floors %2.0f%%/%2.0f%%  MDD %+6.2f%%  train %+7.1f%%  test %+7.1f%%  煞車 %4.1f%%"
          % (s1 * 100, s2 * 100, r["mdd"], tr, te, r["brake_pct"]))
print()
print("=== 4. does nozt (do not stop at the price limit) help? ===")
for nozt in (False, True):
    r, tr, te, tw = ev(dict(BASE, brake=LIVE, nozt=nozt))
    print("  nozt=%-5s  MDD %+6.2f%%  train %+7.1f%%  test %+7.1f%%" % (nozt, r["mdd"], tr, te))
print()
print("=== 5. what the target would be if the opening auction IS reachable (slip 0.33) ===")
for exposure in (1.0, 1.25, 1.5):
    r, tr, te, tw = ev(dict(BASE, brake=LIVE, exposure=exposure, slip_scale=0.33))
    print("  exposure %.2f  MDD %+6.2f%%  train %+7.1f%%  test %+7.1f%%" % (exposure, r["mdd"], tr, te))
