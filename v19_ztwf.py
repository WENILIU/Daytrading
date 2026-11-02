# -*- coding: utf-8 -*-
r"""Walk-forward on zt_min_dist: pick the threshold using 2014-2021 only, then read
2022-2026 as out-of-sample.

The grid plateau is real but the year-on-year deltas swing +-20pp, so the exact threshold
is not identifiable from the full sample. This separates the two claims: "the direction is
right" (does the pre-2022 half prefer the same region?) and "the size of the gain" (what
does the later half actually deliver when the threshold was chosen without seeing it?).
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
ORIG_GROUPS = T.GROUPS

def summarize(tag, y):
    yr = y["yearly"]; v = {k: yr[k] / CAP * 100 for k in yr}
    mi = np.mean([v[k] for k in IN if k in v]); mo = np.mean([v[k] for k in OUT if k in v])
    print("%-22s  2014-21 %+7.1f%%  MDD %6.2f%% | 2022-26 %+7.1f%%  MDD %6.2f%%  比值 %5.1f  筆/日 %4.1f"
          % (tag, mi, y["mdd"], mo, mo / abs(y["mdd"]) if y["mdd"] else 0, y["per_day"]), flush=True)
    return dict(tag=tag, insample=mi, mdd_all=y["mdd"], outsample=mo,
                ratio_out=mo / abs(y["mdd"]), per_day=y["per_day"])

rows = []
print("selection window 2014-2021, holdout 2022-2026", flush=True)
T.GROUPS = ORIG_GROUPS
rows.append(summarize("honest B (無過濾)", T.run(**base)))
for z in [0.03, 0.04, 0.045, 0.05, 0.055, 0.06, 0.07, 0.08]:
    rows.append(summarize("zt_min_dist %.3f" % z, T.run(**dict(base, zt_min_dist=z))))
df = pd.DataFrame(rows)
best = df.iloc[1:]["insample"].idxmax()
print("\n選出的門檻 (僅看 2014-2021): %s  樣本內 %+0.1f%%  持有期 %+0.1f%%"
      % (df.loc[best, "tag"], df.loc[best, "insample"], df.loc[best, "outsample"]), flush=True)
df.to_csv("_ztwf.csv", index=False)
print("saved _ztwf.csv", flush=True)
