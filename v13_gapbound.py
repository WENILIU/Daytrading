"""Where does tightening the gap filter stop helping?

The sweep 0.04 -> none was monotone on both axes, which means the best value may
be outside the range tested. A parameter chosen at the edge of its own sweep is not
chosen, it is assumed. Extend downward until return or drawdown turns.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
TRAIN = range(2014, 2022)
TEST = range(2022, 2027)
LIVE = ((-0.006, 0.30), (-0.012, 0.12))
CH = dict(brake=LIVE, liq=0.10, exposure=1.25, spread=0.0)

print("  %8s %8s %8s %8s %8s %7s %8s" %
      ("gap_max", "MDD%", "train%", "test%", "worst yr", "筆/日", "煞車%"))
for gm in (0.02, 0.025, 0.03, 0.04, 0.05, 0.06):
    r = T.run(**dict(CH, gap_max=gm))
    y = r["yearly"]
    tr = np.mean([y[k] / CAP0 * 100 for k in sorted(y) if k in TRAIN])
    te = np.mean([y[k] / CAP0 * 100 for k in sorted(y) if k in TEST])
    tw = min([y[k] / CAP0 * 100 for k in sorted(y) if k in TEST])
    print("  %8.3f %+8.2f %+8.1f %+8.1f %+8.1f %7.1f %8.1f" %
          (gm, r["mdd"], tr, te, tw, r["per_day"], r["brake_pct"]))

