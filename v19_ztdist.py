# -*- coding: utf-8 -*-
r"""Would a direct "how far is the price limit" filter bind at all?

gap_max is a proxy for this on a market-adjusted scale. The limit does not care
about the market move, and TWSE narrows a name's band to +-5 pct after a big run,
which is exactly when a short is most likely to end locked. If the distribution of
(lu - entry)/entry is all ~5.8 pct then this filter is just gap_max again and is
not worth a parameter. If a real slice sits under 2-3 pct, it is a different and
sharper question.
"""
import pandas as pd, numpy as np
S = pd.read_pickle("signals_v13.pkl")
S["date"] = S["date"].astype(str)
S["stock"] = S["stock"].astype(str)
S["entry"] = pd.to_numeric(S["entry"], errors="coerce")
S["lu"] = pd.to_numeric(S["lu"], errors="coerce")
S["ld"] = pd.to_numeric(S["ld"], errors="coerce")
S["adj_gap"] = pd.to_numeric(S["adj_gap"], errors="coerce")
sh = S[S.direction == "SHORT"].copy()
sh["zdist"] = (sh.lu - sh.entry) / sh.entry
lo = S[S.direction == "LONG"].copy()
lo["zdist"] = (lo.entry - lo.ld) / lo.entry
# the band the strategy actually trades: SHORT 1.5-4 pct market-adjusted gap
trade = sh[(sh.adj_gap.abs() >= 0.015) & (sh.adj_gap.abs() <= 0.04)]
print("SHORT signals in the traded 1.5-4 pct band: %d" % len(trade))
for q in (0, .01, .02, .05, .10, .25, .50, .75, .95, 1.0):
    print("   zdist p%-4s %+.2f%%" % (int(q * 100), trade.zdist.quantile(q) * 100))
for t in (0.010, 0.015, 0.020, 0.025, 0.030, 0.040, 0.050):
    m = trade.zdist < t
    print("   skip if zdist < %.3f : %5d = %.2f%% of traded SHORT signals" % (t, m.sum(), m.mean() * 100))
print()
print("LONG signals: %d" % len(lo))
for t in (0.010, 0.020, 0.030, 0.050):
    m = lo.zdist < t
    print("   skip if zdist < %.3f : %5d = %.2f%%" % (t, m.sum(), m.mean() * 100))
print()
print("=== does a narrow band predict locking? (the 893 limit-bound trades) ===")
import pickle
L = pickle.load(open("_min1_lock.pkl", "rb"))
L["date"] = L["date"].astype(str)
k = S[(S.direction.isin(["SHORT", "LONG"]))][["date", "stock", "direction", "lu", "ld", "entry"]]
L["code"] = L["code"].astype(str)
j = L.merge(k, left_on=["date", "code", "direction"], right_on=["date", "stock", "direction"], how="left")
j["zdist"] = np.where(j.direction == "SHORT", (j.lu - j.entry) / j.entry, (j.entry - j.ld) / j.entry)
j = j.dropna(subset=["zdist", "close_1325", "lim"])
j["pinned"] = np.where(j.direction == "SHORT", j.close_1325 >= j.lim - 1e-9,
                       j.close_1325 <= j.lim + 1e-9)
j["band"] = pd.cut(j.zdist, [-1, .01, .02, .03, .05, .08, 1])
t = j.groupby("band", observed=True).agg(n=("pinned", "size"), pin_rate=("pinned", "mean"))
t["pin_rate"] = (t.pin_rate * 100).round(1)
print(t.to_string())
