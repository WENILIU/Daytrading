# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, pickle
S = pd.read_pickle("signals_v13.pkl")
S["date"] = S["date"].astype(str); S["stock"] = S["stock"].astype(str)
for c in ("entry", "lu", "ld", "adj_gap"):
    S[c] = pd.to_numeric(S[c], errors="coerce")
L = pickle.load(open("_min1_lock.pkl", "rb"))
L["date"] = L["date"].astype(str); L["code"] = L["code"].astype(str)
k = S[["date", "stock", "direction", "lu", "ld", "adj_gap"]].drop_duplicates(
    ["date", "stock", "direction"]).rename(columns={"lu": "sig_lu", "ld": "sig_ld",
                                                    "adj_gap": "sig_ag"})
j = L.merge(k, left_on=["date", "code", "direction"], right_on=["date", "stock", "direction"], how="inner")
print("joined:", len(j), "of", len(L))
j["zdist"] = np.where(j.direction == "SHORT", (j.sig_lu - j.entry) / j.entry,
                      (j.entry - j.sig_ld) / j.entry)
j = j.dropna(subset=["zdist", "close_1325", "lim"])
j["pinned"] = np.where(j.direction == "SHORT", j.close_1325 >= j.lim - 1e-9,
                       j.close_1325 <= j.lim + 1e-9)
j["extra"] = np.where(j.direction == "SHORT", (j.close_1325 - j.nd_open) / j.entry,
                      (j.nd_open - j.close_1325) / j.entry)
for dirn in ("SHORT", "LONG"):
    d = j[j.direction == dirn].copy()
    d["band"] = pd.cut(d.zdist, [-1, .02, .04, .06, .08, .10, 9])
    g = d.groupby("band", observed=True)
    out = pd.DataFrame({"n": g.size(),
                        "pin_rate_pct": g.pinned.mean() * 100,
                        "cond_cost_pct": g.apply(lambda x: -x.loc[x.pinned, "extra"].mean() * 100,
                                                 include_groups=False),
                        "expected_cost_pct": g.apply(
                            lambda x: x.pinned.mean() * (-x.loc[x.pinned, "extra"].mean()) * 100,
                            include_groups=False)})
    print("\n=== %s: does the distance to the price limit predict ending pinned? (n=%d) ===" % (dirn, len(d)))
    print(out.round(3).to_string())
print("""
Read it this way: expected_cost_pct is what a filter at that distance would save per
signal it removes. If the column is flat, the distance carries no information and the
filter is only a breadth cut - the same verdict max_lock_rate already got.""")
