# -*- coding: utf-8 -*-
r"""Two signal-side filters that exist in v13_target and have never been swept.

The corrected model (brake tiers fixed, pin_penalty = 0.00747) prices two costs
the earlier search did not carry. Each of those costs has a filter attached to
it that has never been run:

  max_lock_rate  skip a signal in a name whose 250-session rate of closing
                 pinned on the price limit is above this. That rate is exactly
                 the quantity pin_penalty is charged on, and it is knowable at
                 09:00 from the T-1 panel - it is not hindsight.
  gap_max/_long  the entry-cost table is bucketed by |gap|, and the whole tail
                 sits in |gap| >= 7 pct. The caps are live's, so widening or
                 tightening one side is a real switch, not a modelling choice.

Frame unchanged: book pinned at 450 萬, profits withdrawn, choose on 2014-2021,
report 2022-2026. Target: recent five years >= 100 pct with position MDD inside
-5 pct.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import v13_target as T

CAP = T.CAP0
PIN = 0.00747
BRAKE = ((-0.008, .50), (-0.016, .25))
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08,
            spread=0.00105, nosl=True, brake=BRAKE, pin_penalty=PIN)


def sm(y):
    yr = y["yearly"]; ks = sorted(yr)
    v = [yr[k] / CAP * 100 for k in ks]

    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    return (sum(v) / len(v), avg(2014, 2021), avg(2022, 2026), y["mdd"], min(v),
            y["n_pin"], y["n_lockskip"], sum(yr.values()))


HDR = "%-30s %+6s %+8s %+8s %7s %7s %6s %6s %6s" % (
    "配置", "13yr", "2014-21", "2022-26", "MDD", "最差年", "鎖價筆", "跳過筆", "筆/日")


def show(tag, **kw):
    y = T.run(**dict(base, **kw))
    a, o, r, m, w, np_, nl, tot = sm(y)
    flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ""
    print(("%-30s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %6d %6d %6.1f%s")
          % (tag, a, o, r, m, w, np_, nl, y["per_day"], flag), flush=True)
    return dict(tag=tag, all=a, old=o, recent=r, mdd=m, worst=w, n_pin=np_,
                n_skip=nl, per_day=y["per_day"], total=tot)


rows = []
print("=== 基準（G、已計鎖價成本、修正後的煞車）===")
print(HDR)
rows.append(show("基準 G"))

print("\n=== 鎖板率過濾（跳開常鎖板的股票）===")
print(HDR)
for lr in (0.50, 0.35, 0.25, 0.15, 0.10):
    rows.append(show("lock_rate <= %.2f" % lr, max_lock_rate=lr))

print("\n=== gap 上限（SHORT / LONG 分開）===")
print(HDR)
for s, l in ((0.03, 0.08), (0.05, 0.08), (0.06, 0.08), (0.04, 0.06),
             (0.04, 0.10), (0.04, None)):
    rows.append(show("SHORT<=%.2f LONG=%s" % (s, l if l else "開"),
                     gap_max=s, gap_max_long=l))

pd.DataFrame(rows).to_csv("_lockgap.csv", index=False)
print("\nsaved _lockgap.csv")
