# -*- coding: utf-8 -*-
r"""Remove the backwards boost instead of excluding the trades, scored on both windows.

The sizing model multiplies any position within BP1=1.5pct of the price limit by M1=10 and
within BP2=4.5pct by M2=2.5 (v13_engine.py:158). The trade-level buckets show those names
pin at 33-83pct, so the boost is pointing the wrong way. But the walk-forward on
zt_min_dist just showed the near-limit population only turned bad after 2022: excluding it
wins 2022-2026 and loses 2014-2021. So a fix has to be judged on both halves, not one.

v13_target bakes the multiplier into D["_weight"] at import time, so the boost must be
patched before v13_target is imported. One variant per process, selected by argv.
"""
import sys, warnings; warnings.filterwarnings("ignore")
VARIANT = sys.argv[1]
import v13_engine as E

BOOST = {"orig": None, "m1_25": (0.015, 0.045, 2.5, 2.5), "m1_1": (0.015, 0.045, 1.0, 2.5),
         "nomult": (0.015, 0.045, 1.0, 1.0), "m1_half": (0.015, 0.045, 0.5, 1.0),
         "m1_1_zt03": (0.015, 0.045, 1.0, 2.5)}
ZT = {k: None for k in BOOST}
ZT["m1_1_zt03"] = 0.03
if BOOST[VARIANT] is not None:
    E.BP1, E.BP2, E.M1, E.M2 = BOOST[VARIANT]

import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
PIN = 0.03149 + 0.0015 + 0.30 * 2 / 365.0
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00,
            gap_max_long=0.08, spread=0.00105, cost_mode="measured",
            brake=((-0.008, .50), (-0.016, .25)), gap_max=0.040, order_cap=20,
            nosl=True, pin_short=PIN, pin_long=0.0)
if ZT[VARIANT] is not None:
    base["zt_min_dist"] = ZT[VARIANT]
IN = list(range(2014, 2022)); OUT = list(range(2022, 2027))

y = T.run(**base)
yr = y["yearly"]; v = {k: yr[k] / CAP * 100 for k in yr}
mi = np.mean([v[k] for k in IN if k in v]); mo = np.mean([v[k] for k in OUT if k in v])
print("%-11s boost=%s zt=%s | 2014-21 %+7.1f%% | 2022-26 %+7.1f%%  全期MDD %6.2f%%  筆/日 %4.1f  鎖停S %5d"
      % (VARIANT, BOOST[VARIANT], ZT[VARIANT], mi, mo, y["mdd"], y["per_day"],
         y["n_pin_dir"].get("SHORT", 0)), flush=True)
