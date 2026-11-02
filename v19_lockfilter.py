# -*- coding: utf-8 -*-
r"""Cut the locked-short tail at the source, using a REAL lock-proneness measure.

lock_rate_up_250 is dead (every finite value is 1.0), so the earlier filter test was
an artifact. zt_close_60 (count of limit-up CLOSES in the last 60 days) is real and is
exactly "how often does this stock lock at limit-up" - a short on such a name is the
one that pins and must be carried (borrow + lost day-trade tax + default risk).

Two ways to act on it, both with the honest pin cost (price 3.149 + tax 0.15 +
borrow 30pct x2d = 3.46 pct) so we measure net of the real tail cost:
  filter     : drop SHORT signals whose zt_close_60 exceeds K
  down-weight: shrink the position by (1 - min(1, zt_close_60/C)) on SHORT
Baseline is the honest B book (no action).
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

D0 = T.D.copy()
D0["zc"] = pd.to_numeric(D0["zt_close_60"], errors="coerce").fillna(0.0)

def set_state(filter_k=None, dw_C=None):
    D = D0.copy()
    if filter_k is not None:
        # put real lock-proneness (fraction) into the column max_lock_rate reads
        D["lock_rate_up_250"] = np.where(D["direction"] == "SHORT", D["zc"] / 60.0, np.nan)
        D["lock_rate_dn_250"] = 0.0
    if dw_C is not None:
        f = 1.0 - np.minimum(1.0, D["zc"].values / dw_C)
        D["_weight"] = np.where(D["direction"] == "SHORT", D["_weight"].values * f, D["_weight"].values)
    T.D = D
    T.GROUPS = {d: g[~g["blocked"]] for d, g in D.groupby("date")}

def summarize(tag, y):
    yr = y["yearly"]; ks = sorted(yr); v = [yr[k] / CAP * 100 for k in ks]
    recent = sum(x for k, x in zip(ks, v) if 2022 <= k <= 2026) / len([k for k in ks if 2022 <= k <= 2026])
    m = y["mdd"]; pinS = y["n_pin_dir"].get("SHORT", 0)
    print("%-34s 2022-26 %+7.1f%%  MDD %6.2f%%  比值 %5.1f  筆/日 %4.1f  總筆 %6d  鎖停SHORT %5d"
          % (tag, recent, m, recent/abs(m), y["per_day"], y["n"], pinS), flush=True)
    return dict(tag=tag, recent=recent, mdd=m, ratio=recent/abs(m), per_day=y["per_day"], n=y["n"], pinS=pinS)

rows = []
print("honest pin cost = %.4f" % PIN, flush=True)
set_state(); rows.append(summarize("honest B (基準)", T.run(**base)))
for K in [6, 3, 1]:
    set_state(filter_k=K); rows.append(summarize("過濾 zt_close_60 > %d" % K, T.run(**dict(base, max_lock_rate=K/60.0))))
for C in [6, 3]:
    set_state(dw_C=C); rows.append(summarize("降碼 1-min(1,zt60/%d)" % C, T.run(**base)))
pd.DataFrame(rows).to_csv("_lockfilter2.csv", index=False)
print("saved _lockfilter2.csv", flush=True)
