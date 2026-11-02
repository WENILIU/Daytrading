# -*- coding: utf-8 -*-
r"""zt_min_dist, corrected.

v1 of this script rebuilt GROUPS without dropping the executability-blocked rows, which
inflated every zt_min_dist row by ~2pp. lock(K) did drop them, which is why "lock>6 only"
reproduced the canonical +78.1/-4.20 exactly and exposed the bug. Fixed here by keeping the
module default GROUPS for the unfiltered rows.

The second half answers the mechanism question the grid cannot: are trades entered close to
the price limit actually net negative? capture=True returns the real book, so each taken
trade is bucketed by its own distance to the limit it can hit. If the near buckets lose and
the far buckets carry everything, excluding them is a fix rather than a curve fit.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
PIN = 0.03149 + 0.0015 + 0.30 * 2 / 365.0
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00,
            gap_max_long=0.08, spread=0.00105, cost_mode="measured",
            brake=((-0.008, .50), (-0.016, .25)), gap_max=0.040, order_cap=20,
            nosl=True, pin_short=PIN, pin_long=0.0)
YEARS = [2022, 2023, 2024, 2025, 2026]

D0 = T.D.copy()
D0["zc"] = pd.to_numeric(D0["zt_close_60"], errors="coerce").fillna(0.0)
ORIG_GROUPS = T.GROUPS

def plain():
    T.D = D0
    T.GROUPS = ORIG_GROUPS

def lock(K):
    D = D0.copy()
    D["lock_rate_up_250"] = np.where(D["direction"] == "SHORT", D["zc"] / 60.0, np.nan)
    D["lock_rate_dn_250"] = 0.0
    T.D = D
    T.GROUPS = {d: g[~g["blocked"]] for d, g in D.groupby("date")}

def summarize(tag, y):
    yr = y["yearly"]; v = {k: yr[k] / CAP * 100 for k in yr}
    recent = np.mean([v[k] for k in YEARS if k in v])
    m = y["mdd"]
    print("%-22s %+7.1f%%  MDD %6.2f%%  比值 %5.1f  筆/日 %4.1f  鎖停S %5d  跳 %6d | %s"
          % (tag, recent, m, recent / abs(m), y["per_day"],
             y["n_pin_dir"].get("SHORT", 0), y["n_ztskip"],
             " ".join("%+6.1f" % v[k] for k in YEARS if k in v)), flush=True)
    return dict(tag=tag, recent=recent, mdd=m, ratio=recent / abs(m),
                per_day=y["per_day"], pinS=y["n_pin_dir"].get("SHORT", 0),
                ztskip=y["n_ztskip"], **{str(k): v.get(k) for k in YEARS})

rows = []
print("year order: " + " ".join(str(y) for y in YEARS), flush=True)
plain()
rows.append(summarize("honest B (基準)", T.run(**base)))
for z in [0.04, 0.045, 0.05, 0.055, 0.06]:
    rows.append(summarize("zt_min_dist %.3f" % z, T.run(**dict(base, zt_min_dist=z))))
lock(6)
rows.append(summarize("lock>6 only", T.run(**dict(base, max_lock_rate=6 / 60.0))))
rows.append(summarize("lock>6 + zt0.05", T.run(**dict(base, max_lock_rate=6 / 60.0,
                                                      zt_min_dist=0.05))))
plain()
pd.DataFrame(rows).to_csv("_ztgrid2.csv", index=False)

# --- mechanism: PnL of taken trades bucketed by distance to the limit they can hit ---
res = T.run(**dict(base, capture=True))
tr = pd.DataFrame(res["trades"], columns=["date", "code", "direction", "notional",
                                          "gross", "reason", "entry", "exit"])
tr["date"] = pd.to_datetime(tr["date"]); tr["code"] = tr["code"].astype(str)
key = D0.set_index(["date", D0["stock"].astype(str)])[["lu", "ld"]]
tr = tr.join(key, on=["date", "code"])
tr["pnl_pct"] = tr["notional"] * tr["gross"] / (tr["notional"] / tr["entry"]) * tr["entry"] / 1.0
tr["ret"] = np.where(tr["direction"] == "SHORT",
                     (tr["entry"] - tr["exit"]) / tr["entry"],
                     (tr["exit"] - tr["entry"]) / tr["entry"])
tr["zdist"] = np.where(tr["direction"] == "SHORT",
                       (tr["lu"] - tr["entry"]) / tr["entry"],
                       (tr["entry"] - tr["ld"]) / tr["entry"])
tr["pin"] = tr["reason"].astype(str).str.contains("PIN", case=False, na=False)
print("\n=== 依「距漲停/跌停」分組（實際成交的书，含成本前 gross） ===", flush=True)
bins = [0, .015, .03, .05, .08, .12, 1.0]
tr["b"] = pd.cut(tr["zdist"], bins)
for side in ["SHORT", "LONG"]:
    s = tr[tr["direction"] == side]
    print("--- %s (n=%d) ---" % (side, len(s)), flush=True)
    g = s.groupby("b", observed=True).agg(n=("ret", "size"), win=("ret", lambda x: (x > 0).mean() * 100),
                                          avg=("ret", "mean"), pin=("pin", "mean"))
    for b, r in g.iterrows():
        print("  距漲停 %-14s n=%6d  勝率 %5.1f%%  平均 %+6.2f%%  鎖停率 %5.1f%%"
              % (str(b), int(r["n"]), r["win"], r["avg"] * 100, r["pin"] * 100), flush=True)
tr.to_csv("_ztdist_trades.csv", index=False)
print("saved _ztgrid2.csv _ztdist_trades.csv", flush=True)
