# -*- coding: utf-8 -*-
r"""What is inside the one day that defines the drawdown?

The book spends 2,520 of 2,521 days above 95 pct of the line. The whole MDD is
2021-05-18, -225,076 TWD in one session. An equity-drawdown brake cannot help:
on that morning the book was AT the peak, so it traded at full size by design.
Anything that reduces this number has to act before the orders go out, so the
first question is what the day actually was - one direction, one move, or a
diffuse bad day. The panel carries the market return and the model's own inputs,
so the answer is in the data we already have.
"""
import warnings; warnings.filterwarnings("ignore")
import collections
import numpy as np, pandas as pd
import v13_target as T

DAY = "2021-05-18"
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08, spread=0.00105,
            nosl=True, pin_penalty=0.00747, capture=True,
            brake=((-0.006, .45), (-0.012, .22)))
y = T.run(**base)
tr = pd.DataFrame([dict(zip("date code dir notional gross reason entry exit".split(), t))
                   for t in y["trades"]])
tr["pnl"] = tr["notional"] * tr["gross"]
day = tr[tr["date"] == DAY].copy()
print("=== %s ===" % DAY)
print("trades %d, pnl %.0f TWD (%.2f%% of 450W)" % (len(day), day["pnl"].sum(), day["pnl"].sum() / 4.5e6 * 100))
print("by direction:")
for k, g in day.groupby("dir"):
    print("   %-6s n=%2d  pnl %+10.0f  mean gross %+.3f%%  worst %+.2f%%"
          % (k, len(g), g["pnl"].sum(), g["gross"].mean() * 100, (g["gross"] * 100).min()))
print("exposure on the day: %.0f W notional (%.0f%% of the line)"
      % (day["notional"].sum() / 1e4, day["notional"].sum() / 4.5e6 * 100))
print("\nmarket context (from the panel):")
d = T.D.copy()
d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
r = d[d["date"] == DAY]
for c in ("market_ret", "mkt_drawdown", "consec_down_days", "prev3_market_ret", "signals_today"):
    if c in r.columns and len(r):
        print("   %-20s %s" % (c, r[c].iloc[0]))
print("\nthe ten worst trades that day:")
cols = ["code", "dir", "notional", "gross", "pnl", "reason"]
print(day.nsmallest(10, "pnl")[cols].to_string(index=False))

# is this day special, or is one-direction concentration normal?
print("\n--- how concentrated is a bad day usually? ---")
by_day = tr.groupby("date").agg(pnl=("pnl", "sum"), n=("pnl", "size"))
dir_share = tr.assign(s=np.where(tr["dir"] == "SHORT", 1, -1)).groupby("date")["s"].mean().abs()
by_day["dir_conc"] = dir_share
worst = by_day.nsmallest(8, "pnl")
print(worst.to_string())
print("\ncorrelation between direction concentration and daily pnl: %s"
      % round(np.corrcoef(by_day["dir_conc"], by_day["pnl"])[0, 1], 3))
mr = d.groupby("date")["market_ret"].first()
mr.index = pd.to_datetime(mr.index).strftime("%Y-%m-%d")
common = by_day.index.intersection(mr.index)
print("market return on the 8 worst days:", [round(mr[x] * 100, 2) for x in worst.index if x in mr.index])
print("market return across all days: mean %+.3f%%, p1 %+.3f%%" % (mr.mean() * 100, mr.quantile(.01) * 100))
