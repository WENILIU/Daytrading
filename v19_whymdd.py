# -*- coding: utf-8 -*-
r"""Why is the drawdown identical for every brake?

A number that does not move when position size moves is not a risk measurement -
it is one event that sizing never had a chance to touch. Reproduce the book day
by day and find out when -5.0017 pct actually happened.
"""
import warnings; warnings.filterwarnings("ignore")
import v13_target as T

CAP = T.CAP0
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08, spread=0.00105,
            nosl=True, pin_penalty=0.00747, capture=True, brake=((-0.006, .45), (-0.012, .22)))
y = T.run(**base)
print("mdd reported:", y["mdd"], "brake_days:", round(y["brake_pct"], 1), "%")

# rebuild the book exactly as run() does, but keep the dates
import numpy as np, pandas as pd, collections
yuan_by_day = collections.defaultdict(float)
for d, code, dr, notional, gross, reason, entry, ex in y["trades"]:
    yuan_by_day[d] += notional * gross
days = sorted(yuan_by_day)
book = CAP; peak = CAP; hist = []
for d in days:
    book = min(CAP, book + yuan_by_day[d])
    peak = max(peak, book)
    hist.append((d, yuan_by_day[d], book, (book - peak) / peak * 100))
h = pd.DataFrame(hist, columns="date yuan book dd".split())
worst = h.nsmallest(6, "dd")
print("\nworst drawdown days:")
print(worst.to_string(index=False))
print("\nfirst 8 trading days of the sample:")
print(h.head(8).to_string(index=False))
print("\nhow often is the book below 95 pct of the line: %d of %d days"
      % ((h["book"] < CAP * 0.95).sum(), len(h)))
print("the deepest point is on:", worst.iloc[0]["date"])
