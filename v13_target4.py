"""The target, priced with the entry cost that was actually measured.

Sections:
 1. what the measured cost costs relative to the old curve - this is the honest
    size of the correction, and it is the reason earlier numbers looked reachable
 2. the exposure ladder under the measured cost, to find the smallest book that
    clears 100 pct a year on 2022-2026 with the position drawdown inside -5 pct
 3. the chosen configuration in full: every year, orders per day, peak deployment,
    and whether anything here needs borrowing
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


print("=== 1. the size of the correction (exposure 1.0, zero margin, liq 0.10) ===")
for lbl, cfg in (("old curve, slip_scale 0.33", dict(cost_mode="curve", slip_scale=0.33)),
                 ("old curve, slip_scale 1.00", dict(cost_mode="curve", slip_scale=1.0)),
                 ("measured, price only", dict(cost_mode="measured", spread=0.0)),
                 ("measured, price + half-spread", dict(cost_mode="measured"))):
    r, tr, te, tw = ev(brake=LIVE, liq=0.10, gap_max=None, exposure=1.0, **cfg)
    print("  %-32s MDD %+6.2f%%  train %+7.1f%%  test %+7.1f%%" % (lbl, r["mdd"], tr, te))

print()
print("=== 2. exposure ladder under the measured cost ===")
print("  %8s %6s %8s %8s %8s %8s %8s %7s %9s %7s" %
      ("exposure", "liq", "gapmax", "MDD%", "train%", "test%", "worst yr", "筆/日", "曝險max%", "煞車%"))
rows = []
for exposure in (1.0, 1.25, 1.5, 1.75, 2.0):
    for liq in (0.10, 0.25):
        for gap_max in (None, 0.10, 0.07):
            cfg = dict(brake=LIVE, liq=liq, gap_max=gap_max, exposure=exposure)
            r, tr, te, tw = ev(**cfg)
            flag = "  <= clears" if (te >= 100.0 and r["mdd"] >= -5.0) else ""
            print("  %8.2f %6s %8s %+8.2f %+8.1f %+8.1f %+8.1f %7.1f %9.1f %7.1f%s" %
                  (exposure, liq, gap_max if gap_max else "-", r["mdd"], tr, te, tw,
                   r["per_day"], r["expo_max"], r["brake_pct"], flag))
            rows.append((exposure, liq, gap_max, r, tr, te, tw))
print()
clear = sorted([x for x in rows if x[5] >= 100.0 and x[3]["mdd"] >= -5.0], key=lambda x: x[0])
print("  configs that clear the target: %d" % len(clear))
if clear:
    e, l, g, r, tr, te, tw = clear[0]
    print("  smallest: exposure %.2f liq=%s gap_max=%s -> test %+.1f%%, MDD %+.2f%%, max deployment %.0f%%"
          % (e, l, g, te, r["mdd"], r["expo_max"]))

print()
print("=== 3. brake robustness on the smallest clearing configuration ===")
if clear:
    e, l, g, _, _, _, _ = clear[0]
    for mult in (0.5, 0.75, 1.0, 1.5, 2.0):
        bk = ((LIVE[0][0] * mult, LIVE[0][1]), (LIVE[1][0] * mult, LIVE[1][1]))
        r2, tr2, te2, tw2 = ev(brake=bk, liq=l, gap_max=g, exposure=e)
        print("  thresholds x%-4.2f  MDD %+6.2f%%  train %+7.1f%%  test %+7.1f%%  煞車 %4.1f%%"
              % (mult, r2["mdd"], tr2, te2, r2["brake_pct"]))
