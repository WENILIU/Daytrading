"""Exposure is free on risk (MDD flat) but it does make the orders bigger, and bigger
orders are the one thing that can stop working in real trading. Check participation and
how often the ceiling actually binds before shipping 1.90 instead of 1.75."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
LIVE = ((-0.006, 0.30), (-0.012, 0.12))
BASE = dict(brake=LIVE, liq=0.10, gap_max=0.04, gap_max_long=0.08, spread=0.0)

print("  %8s %8s %9s %8s %8s %8s %8s %8s" % ("exposure", "MDD%", "13yr", "筆/日", "part p50", "p90", "p99", "max"))
for ex in (1.0, 1.25, 1.5, 1.75, 1.9, 2.0):
    r = T.run(**dict(BASE, exposure=ex))
    y = r["yearly"]
    al = np.mean([y[k] / CAP0 * 100 for k in sorted(y)])
    print("  %8.2f %+8.2f %+9.1f %8.1f %8.1f %8.1f %8.1f %8.1f"
          % (ex, r["mdd"], al, r["per_day"], r.get("part50", float("nan")), r["part90"],
             r.get("part99", float("nan")), r.get("partmax", float("nan"))))
