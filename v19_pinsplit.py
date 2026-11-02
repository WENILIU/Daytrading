# -*- coding: utf-8 -*-
r"""Separate "reaches limit-up and STAYS" (pin) from "reaches limit-up then FALLS back".

Result (2026-11-02): the profitable "touch-and-fall" case 文義 hoped for does not
exist. Once a SHORT's stock reaches the upper limit it loses whether it stays (-10.5 pct
with the honest carry cost) or falls back (-3.4 pct, 15 pct win) - reaching the limit
against a short is itself the losing event. 92.9 pct of shorts never approach the limit
and carry the whole edge (+0.74 pct, 62 pct win). zt_close_60 is elevated for BOTH
limit-reaching groups, so the zt_close_60 filter removes net-negative trades, which is
why it improves MDD at ~zero return cost. Implication: the x10 near-limit sizing is
backwards - near-limit shorts should be excluded (zt_min_dist), not boosted.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

d = pd.read_pickle("signals_v13.pkl")
d = d[d["pred"].notna()].copy()
sh = d[(d["direction"] == "SHORT") & (d["adj_gap"].abs() <= 0.04)].copy()
e = sh["entry"].values; hi = sh["day_high"].values; lo = sh["day_low"].values
cl = sh["day_close"].values; lu = sh["lu"].values; tp = sh["tp"].values
COST = 2 * 0.00111
PIN = 0.03149 + 0.0015 + 0.30 * 2 / 365.0

touched = hi >= lu - 1e-9
stayed = cl >= lu - 1e-9
hit_tp = lo <= e * (1 - tp)
pnl = np.where(hit_tp, tp, (e - cl) / e) - COST
pnl_true = pnl - np.where(stayed, PIN, 0.0)

def rep(name, m):
    if m.sum() == 0:
        print("%-22s n=0" % name); return
    print("%-22s n=%6d (%4.1f%%)  均價差 %+6.2f%%  含承銷 %+6.2f%%  勝率 %4.1f%%"
          % (name, m.sum(), 100*m.mean(), 100*pnl[m].mean(), 100*pnl_true[m].mean(),
             100*(pnl_true[m] > 0).mean()))

print("tradeable SHORT:", len(sh))
rep("never touched limit", ~touched)
rep("touch then FELL back", touched & ~stayed)
rep("STAYED at limit (pin)", stayed)
zc = pd.to_numeric(sh["zt_close_60"], errors="coerce").fillna(0.0).values
print("zt_close_60 mean: never %.2f | touch-fall %.2f | stayed %.2f"
      % (zc[~touched].mean(), zc[touched & ~stayed].mean(), zc[stayed].mean()))
