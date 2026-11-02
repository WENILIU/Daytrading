# -*- coding: utf-8 -*-
r"""What does being unable to buy back actually cost?

v17_lock.py already walked 897 price-limit-bound trades through the 1-minute bars
and recorded the 13:25 price and the next day's open. That is the exact question
Weni keeps asking: not "how big is the loss" but "what if it does not come back
and I have to carry it". Answer it in TWD on the notional we actually held.

Carrying from 13:25 to the next open costs, relative to the entry:
  LONG  (wanted to sell at 13:25): (nd_open - close_1325) / entry
  SHORT (wanted to buy  at 13:25): (close_1325 - nd_open) / entry
"""
import pickle
import numpy as np, pandas as pd

df = pickle.load(open("_min1_lock.pkl", "rb"))
df["date"] = df["date"].astype(str)
print("rows:", len(df), "dates:", df["date"].min(), "->", df["date"].max())
print("locked flag:", dict(df["locked"].value_counts()))

d = df.dropna(subset=["nd_open", "close_1325"]).copy()
short = d["direction"] == "SHORT"
d["extra"] = np.where(short, (d["close_1325"] - d["nd_open"]) / d["entry"],
                     (d["nd_open"] - d["close_1325"]) / d["entry"])
d["extra_twd"] = d["extra"] * d["notional"]
# still pinned at the close: the 13:25 price IS the limit, so a clear could not fill
d["pinned"] = np.where(short, d["close_1325"] >= d["lim"] - 1e-9,
                       d["close_1325"] <= d["lim"] + 1e-9)
print("\nwith next-day data:", len(d), "of", len(df))
print("still pinned at 13:25 (clear cannot fill): %d = %.1f%%" % (d["pinned"].sum(), d["pinned"].mean() * 100))
print("  by direction:", dict(d.loc[d["pinned"], "direction"].value_counts()))
print("  by year:", dict(sorted(pd.Series(d.loc[d["pinned"], "date"].str[:4]).value_counts().items())))

for lab, sub in [("PINNED at close (forced overnight)", d[d["pinned"]]),
                 ("unlocked before close (clear fills)", d[~d["pinned"]])]:
    if not len(sub):
        continue
    e = sub["extra"] * 100
    print("\n%s  n=%d" % (lab, len(sub)))
    print("  overnight move vs 13:25: mean %+.3f%%  median %+.3f%%  p5 %+.2f%%  worst %+.2f%%  best %+.2f%%"
          % (e.mean(), e.median(), e.quantile(.05), e.min(), e.max()))
    print("  TWD on the notionals we held: total %+.0f, mean %+.0f, worst %+.0f"
          % (sub["extra_twd"].sum(), sub["extra_twd"].mean(), sub["extra_twd"].min()))
    print("  it would have been BETTER to carry: %.1f%% of them" % ((sub["extra"] > 0).mean() * 100))
    if lab.startswith("PINNED"):
        print("  by direction:", {k: "%+.3f%% mean" % (g["extra"].mean() * 100)
                                  for k, g in sub.groupby("direction")})
        print("  worst 5:")
        w = sub.nsmallest(5, "extra")[["date", "code", "direction", "entry", "close_1325", "nd_open", "extra", "extra_twd"]]
        print(w.to_string(index=False))
