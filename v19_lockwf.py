# -*- coding: utf-8 -*-
r"""Score the lock filter on both windows - the test zt_min_dist just failed.

zt_min_dist wins 2022-2026 and loses 2014-2021, so a walk-forward would reject it. The
remaining candidate is the zt_close_60 filter, which earlier showed nearly free MDD
improvement on the full sample. "Nearly free on the full sample" is exactly the claim a
split sample exists to test, so the same two windows are used here: choose on 2014-2021,
read 2022-2026. If the lock filter holds in both, it is the one real improvement left;
if it only helps after 2022, then nothing in this direction is robust and the recent
decay is regime, not a fixable defect.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
PIN = 0.03149 + 0.0015 + 0.30 * 2 / 365.0
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00,
            gap_max_long=0.08, spread=0.00105, cost_mode="measured",
            brake=((-0.008, .50), (-0.016, .25)), gap_max=0.040, order_cap=20,
            nosl=True, pin_short=PIN, pin_long=0.0)
IN = list(range(2014, 2022)); OUT = list(range(2022, 2027))
D0 = T.D.copy()
D0["zc"] = pd.to_numeric(D0["zt_close_60"], errors="coerce").fillna(0.0)
ORIG_GROUPS = T.GROUPS

def plain():
    T.D = D0; T.GROUPS = ORIG_GROUPS

def lock(K):
    D = D0.copy()
    D["lock_rate_up_250"] = np.where(D["direction"] == "SHORT", D["zc"] / 60.0, np.nan)
    D["lock_rate_dn_250"] = 0.0
    T.D = D
    T.GROUPS = {d: g[~g["blocked"]] for d, g in D.groupby("date")}

def summarize(tag, y):
    yr = y["yearly"]; v = {k: yr[k] / CAP * 100 for k in yr}
    mi = np.mean([v[k] for k in IN if k in v]); mo = np.mean([v[k] for k in OUT if k in v])
    print("%-20s 2014-21 %+7.1f%% | 2022-26 %+7.1f%%  全期MDD %6.2f%%  比值 %5.1f  筆/日 %4.1f  鎖停S %5d  跳 %6d | %s"
          % (tag, mi, mo, y["mdd"], mo / abs(y["mdd"]), y["per_day"],
             y["n_pin_dir"].get("SHORT", 0), y["n_lockskip"],
             " ".join("%+6.1f" % v[k] for k in OUT if k in v)), flush=True)
    return dict(tag=tag, insample=mi, outsample=mo, mdd=y["mdd"],
                ratio=mo / abs(y["mdd"]), per_day=y["per_day"])

rows = []
print("holdout years: " + " ".join(str(y) for y in OUT), flush=True)
plain()
rows.append(summarize("honest B (基準)", T.run(**base)))
for K in [12, 10, 8, 6, 4, 3]:
    lock(K)
    rows.append(summarize("lock zt60 > %d" % K, T.run(**dict(base, max_lock_rate=K / 60.0))))
plain()
pd.DataFrame(rows).to_csv("_lockwf.csv", index=False)
print("saved _lockwf.csv", flush=True)
