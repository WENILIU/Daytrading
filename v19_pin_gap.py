# -*- coding: utf-8 -*-
r"""Is the -0.747 pct pin charge the right price for a LARGE-gap short?

Removing the SHORT gap cap is worth a lot in the corrected model, but the cap
was put there for a reason, and the reason is the tail: a name that gapped +12
pct is a name that can lock at 漲停 and not come back. The model charges those
trades the SAME average pin cost as a 2 pct gap, because pin_penalty is one
number. If the pin tail is actually worse in the large-gap band, the no-cap
result is an average that hides it.

Same definition of "carrying costs" as v19_overnight.py:
  LONG  (nd_open - close_1325) / entry      SHORT  (close_1325 - nd_open) / entry
joined to the signal table on (date, code) to get the gap that made the signal.
"""
import pickle
import numpy as np, pandas as pd

lk = pickle.load(open("_min1_lock.pkl", "rb"))
lk["date"] = lk["date"].astype(str)
sig = pickle.load(open("signals_v13.pkl", "rb"))
sig["date"] = pd.to_datetime(sig["date"]).dt.strftime("%Y-%m-%d")
sig["stock"] = sig["stock"].astype(str)
g = sig.groupby(["date", "stock", "direction"])["adj_gap"].mean().reset_index()
g["code"] = g["stock"]

d = lk.merge(g[["date", "code", "direction", "adj_gap"]],
             on=["date", "code", "direction"], how="inner")
d = d.dropna(subset=["nd_open", "close_1325", "adj_gap"]).copy()
short = d["direction"] == "SHORT"
d["extra"] = np.where(short, (d["close_1325"] - d["nd_open"]) / d["entry"],
                     (d["nd_open"] - d["close_1325"]) / d["entry"])
d["pinned"] = np.where(short, d["close_1325"] >= d["lim"] - 1e-9,
                      d["close_1325"] <= d["lim"] + 1e-9)
d["ag"] = d["adj_gap"].abs()
print("price-limit-bound trades joined to a signal: %d of %d" % (len(d), len(lk)))
print("  SHORT %d | LONG %d" % (int(short.sum()), int((~short).sum())), flush=True)

BINS = [0.015, 0.03, 0.04, 0.05, 0.06, 0.08, 0.12, 0.99]
LAB = ["1.5-3", "3-4", "4-5", "5-6", "6-8", "8-12", "12+"]
d["band"] = pd.cut(d["ag"], bins=BINS, labels=LAB, right=False)

HDR = "%-7s %6s %8s %10s %9s %8s %8s %8s" % (
    "gap%", "n", "鎖死率", "過夜均%", "過夜p5%", "最差%", "期望成本%", "較好%")
print("\n=== 全部（兩個方向混在一起）===", flush=True)
print(HDR, flush=True)
for lab in LAB:
    s = d[d["band"] == lab]
    if len(s) < 5:
        continue
    p = s[s["pinned"]]
    if not len(p):
        continue
    e = p["extra"] * 100
    print("%-7s %6d %7.1f%% %+9.3f%% %+8.2f%% %+8.2f%% %+8.3f%% %7.1f%%"
          % (lab, len(s), s["pinned"].mean() * 100, e.mean(), e.quantile(.05),
             e.min(), (s["pinned"].mean() * p["extra"].mean()) * 100,
             (p["extra"] > 0).mean() * 100), flush=True)

print("\n=== 只有 SHORT（要回補的那一側）===", flush=True)
print(HDR, flush=True)
ds = d[d["direction"] == "SHORT"]
for lab in LAB:
    s = ds[ds["band"] == lab]
    if len(s) < 5:
        continue
    p = s[s["pinned"]]
    if not len(p):
        continue
    e = p["extra"] * 100
    print("%-7s %6d %7.1f%% %+9.3f%% %+8.2f%% %+8.2f%% %+8.3f%% %7.1f%%"
          % (lab, len(s), s["pinned"].mean() * 100, e.mean(), e.quantile(.05),
             e.min(), (s["pinned"].mean() * p["extra"].mean()) * 100,
             (p["extra"] > 0).mean() * 100), flush=True)

print("\n整體基準：鎖死率 %.1f%%、鎖死後過夜均 %.3f%%、期望成本 %.3f%%"
      % (d["pinned"].mean() * 100,
         d.loc[d["pinned"], "extra"].mean() * 100,
         d["pinned"].mean() * d.loc[d["pinned"], "extra"].mean() * 100), flush=True)
d.to_csv("_pin_by_gap.csv", index=False)
print("saved _pin_by_gap.csv", flush=True)
