# -*- coding: utf-8 -*-
r"""Conditional cost of being pinned, by direction.

v13_target charges one flat pin_penalty to every trade that closes on a price
limit. But the flat number (0.00747) is 0.323 x 2.311 - the average over ALL
trades that touched a limit, scaled by how many of them stayed pinned. Applying
that to the subset that IS pinned understates it by about 3x. The right number
is the conditional mean given pinned, and it is not the same for the two sides.
"""
import pickle, numpy as np, pandas as pd

df = pickle.load(open("_min1_lock.pkl", "rb"))
df["date"] = df["date"].astype(str)
d = df.dropna(subset=["nd_open", "close_1325"]).copy()
short = d["direction"] == "SHORT"
d["extra"] = np.where(short, (d["close_1325"] - d["nd_open"]) / d["entry"],
                     (d["nd_open"] - d["close_1325"]) / d["entry"])
d["pinned"] = np.where(short, d["close_1325"] >= d["lim"] - 1e-9,
                      d["close_1325"] <= d["lim"] + 1e-9)

print("touched a limit:", len(df), " usable:", len(d))
print("still pinned at 13:25: %d (%.1f%%)" % (d.pinned.sum(), d.pinned.mean()*100))
p = d[d.pinned]
print("pinned by direction:", dict(p.direction.value_counts()))
print()
print("=== the number v13_target SHOULD charge (conditional on being pinned) ===")
for dirn in ("SHORT", "LONG"):
    s = p.loc[p.direction == dirn, "extra"] * 100
    if not len(s):
        continue
    print("%-5s n=%-4d mean %+.3f%%  median %+.3f%%  p05 %+.2f%%  p01 %+.2f%%  worst %+.2f%%  best %+.2f%%"
          % (dirn, len(s), s.mean(), s.median(), s.quantile(.05), s.quantile(.01), s.min(), s.max()))
    print("        -> penalty to SUBTRACT from gross = %+.5f  (%.3f%%)" % (-s.mean()/100, -s.mean()))
print()
print("flat number currently in v13_target: 0.00747 ( = 0.323 x 2.311%%, the UNconditional mean )")
allm = d["extra"]*100
print("unconditional mean over ALL limit-bound trades: %+.3f%%" % allm.mean())
print()
print("=== by year (pinned only) ===")
t = p.assign(yr=p.date.str[:4]).groupby(["yr","direction"])["extra"].agg(["count","mean"])
t["mean"] = t["mean"]*100
print(t.to_string())
print()
print("=== recent 5y (2022+) conditional ===")
r5 = p[p.date >= "2022"]
for dirn in ("SHORT","LONG"):
    s = r5.loc[r5.direction==dirn,"extra"]*100
    if len(s): print("%-5s n=%-4d mean %+.3f%%  -> penalty %+.5f" % (dirn, len(s), s.mean(), -s.mean()/100))
print()
print("=== how much of the pinned cost is a tail event? ===")
for dirn in ("SHORT","LONG"):
    s = p.loc[p.direction==dirn,"extra"]*100
    if not len(s): continue
    print("%-5s worse than -5%%: %.1f%%   worse than -10%%: %.1f%%   gap-up next open: %.1f%%"
          % (dirn, (s<-5).mean()*100, (s<-10).mean()*100, (s<0).mean()*100))
