# -*- coding: utf-8 -*-
r"""Price the locked-short carry honestly.

The published B-arm charges PIN_SHORT_MEASURED = 3.149 pct on a short still pinned at
13:25. That is the price gap to the next open ONLY. It omits:
  - overnight borrow interest on a hot name (文義: 12 pct and up, annualised)
  - the 當沖 tax discount being lost once the position is NOT day-traded (sell tax
    goes 0.15 -> 0.30 pct, so +0.15 pct)
  - 違約 / not-borrowable risk (a binary you cannot price as a fee)

This re-runs the SAME B book (nosl, gap .04, oc 20) with pin_short raised to each
scenario and reports the recent CAGR / MDD and the pinned population, so the aggregate
drag is measured, not argued.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00,
            gap_max_long=0.08, spread=0.00105, cost_mode="measured",
            brake=((-0.008, .50), (-0.016, .25)), gap_max=0.040, order_cap=20, nosl=True)

def summarize(tag, y):
    yr = y["yearly"]; ks = sorted(yr); v = [yr[k] / CAP * 100 for k in ks]
    recent = sum(x for k, x in zip(ks, v) if 2022 <= k <= 2026) / len([k for k in ks if 2022 <= k <= 2026])
    m = y["mdd"]
    npin = y.get("n_pin_dir", {})
    print("%-40s 2022-26 %+7.1f%%  MDD %6.2f%%  比值 %5.1f  pinned=%s"
          % (tag, recent, m, recent/abs(m), npin), flush=True)
    return dict(tag=tag, recent=recent, mdd=m, pinned=str(npin))

# borrow scenarios: annualised rate x assumed carry days / 365, plus the 0.15 pct tax delta.
def pin_cost(price=0.03149, rate=0.0, days=1.0, tax=0.0015):
    return price + tax + rate * days / 365.0

SCEN = [
    ("B 現行（只有價格 3.149%）", 0.03149),
    ("+ 當沖稅失效 +0.15%", pin_cost(tax=0.0015)),
    ("+ 稅 + 借券12% x1日", pin_cost(rate=0.12, days=1)),
    ("+ 稅 + 借券30% x2日", pin_cost(rate=0.30, days=2)),
    ("+ 稅 + 借券50% x3日", pin_cost(rate=0.50, days=3)),
    ("壓力測試 8%（含違約近似）", 0.08),
]
rows = []
for tag, pc in SCEN:
    rows.append(summarize(tag, T.run(**dict(base, pin_short=pc))))
pd.DataFrame(rows).to_csv("_pin_cost.csv", index=False)
print("saved _pin_cost.csv", flush=True)
