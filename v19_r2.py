# -*- coding: utf-8 -*-
r"""Would a buy-back order placed BELOW the limit have filled?

Weni's own proposal, from the 4960 discussion: do not queue at the limit, queue
one notch under it, and if the limit is reached but the price comes back through
that level you are out intraday. v17_lock.py already recorded, for every one of
the 897 price-limit-bound trades, the first time the price came back through
lim*(1-x) for x in 0.5/1.0/1.5/2.0/3.0 pct (hit_*), and the return of taking it
(r2_*). So this is measurable, not arguable.

Compare, on the trades that are still pinned at 13:25 (the ones that would be
forced overnight): carry to the next open vs place the order x pct under the limit.
"""
import pickle
import numpy as np, pandas as pd

df = pickle.load(open("_min1_lock.pkl", "rb"))
df["date"] = df["date"].astype(str)
d = df.dropna(subset=["nd_open", "close_1325"]).copy()
short = d["direction"] == "SHORT"
d["carry"] = np.where(short, (d["close_1325"] - d["nd_open"]) / d["entry"],
                     (d["nd_open"] - d["close_1325"]) / d["entry"])
d["pinned"] = np.where(short, d["close_1325"] >= d["lim"] - 1e-9,
                       d["close_1325"] <= d["lim"] + 1e-9)
p = d[d["pinned"]].copy()
print("pinned at 13:25 (would be forced overnight): %d" % len(p))
print("carry to next open: mean %+.3f%%  total %+.0f TWD\n"
      % (p["carry"].mean() * 100, (p["carry"] * p["notional"]).sum()))

print("在價限下方 x%% 掛回補（r2_*），只算真的鎖到收盤的 %d 筆：" % len(p))
print("  x%   觸發率   平均結果   對照 carry   改善      總 TWD      比 carry 好的占比")
for x in (0.005, 0.010, 0.015, 0.020, 0.030):
    r2 = p["r2_%.3f" % x].astype(float)
    hit = p["hit_%.3f" % x].notna()
    # not filled -> still carried overnight
    eff = np.where(hit, r2, p["carry"])
    better = (eff > p["carry"]).mean()
    print("  %.1f  %6.1f%%   %+7.3f%%   %+7.3f%%   %+7.3f%%  %+10.0f   %5.1f%%"
          % (x * 100, hit.mean() * 100, np.nanmean(r2) * 100, p["carry"].mean() * 100,
             (np.nanmean(r2) - p["carry"].mean()) * 100, (eff * p["notional"]).sum(), better * 100))

print("\n全部 893 筆（含沒鎖住的）看同一件事：")
print("  carry 平均 %+.3f%%" % (d["carry"].mean() * 100))
for x in (0.005, 0.010, 0.015, 0.020, 0.030):
    r2 = d["r2_%.3f" % x].astype(float)
    hit = d["hit_%.3f" % x].notna()
    eff = np.where(hit, r2, d["carry"])
    print("  x=%.1f%%  觸發 %5.1f%%  平均 %+.3f%%  比 carry 好 %5.1f%%"
          % (x * 100, hit.mean() * 100, np.nanmean(r2) * 100, (eff > d["carry"]).mean() * 100))
