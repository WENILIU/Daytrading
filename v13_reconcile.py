"""Why does the executable book start 20pp below the published R9 number?

Reproduce the published figure by turning the new costs off one at a time, on the
same capture window the published run used. If A0 does not land on 121.9% / -6.54%
then the difference is not the costs and something else changed - which would make
every number below untrustworthy.

Usage: python v13_reconcile.py
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_executable as X
from v13_engine import run_backtest, stats, exit_of_legal, CAP0, COST
import v13_sizing as S

CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
_, got, _ = run_backtest(capture=("2014-01-01", "2026-12-31"), capital=CAP0, **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
BASE = {k: v for k, v in S.R9.items() if k not in ("min_turnover_factor", "dv_cap", "dv_skip")}

def go(order_cap, floor, fc, slc, slip_scale, label):
    rule = dict(BASE)
    if floor is not None:
        rule["min_turnover_factor"] = floor
    rows = []; n_all = 0
    for d, g in D.groupby("date"):
        g = g.sort_values("_rank"); rem = CAP0; n_day = 0; yuan = 0.0
        for _, r in g.iterrows():
            if n_day >= order_cap:
                break
            pr = float(r["entry"]); code = str(r["stock"])
            dv1 = float(TO1.at[d, code]) if (code in TO1.columns and d in TO1.index) else np.nan
            n = S.lots_for(rule, float(r["_weight"]), pr, rem, dv1, capital=CAP0)
            if n <= 0:
                continue
            sh = n * 1000.0
            ex, slp, tpp, reason, gross = exit_of_legal(
                r["direction"], pr, float(r["day_high"]), float(r["day_low"]), float(r["day_close"]),
                float(r["lu"]), float(r["ld"]), float(r["tick"]), float(r["tp"]))
            if reason == "13:25 強制平倉":
                gross -= fc
            elif reason.startswith("停損"):
                gross -= slc
            gross -= 2 * COST + X.slip_cost(
                (sh * pr) / (X.K_OPEN * dv1) if (np.isfinite(dv1) and dv1 > 0) else np.nan, slip_scale)
            rem -= sh * pr; yuan += sh * pr * gross; n_day += 1; n_all += 1
        rows.append((d, yuan / CAP0))
    s = pd.Series([x[1] for x in rows], index=pd.to_datetime([x[0] for x in rows]))
    st = stats(s)
    print("%-42s CAGR %7.1f%%  MDD %6.2f%%  Sharpe %5.2f  筆/日 %4.1f" %
          (label, st["cagr"], st["mdd"], st["sharpe"], n_all / len(s)))

print("目標：之前發表的 R9（f=5.0、含 30 筆上限）= CAGR 121.9%% / MDD -6.54%%")
go(30, 5.0, 0.0, 0.0, 0.0, "A0 完全重現舊設定（無任何新成本）")
go(30, 5.0, X.FC_COST, 0.0, 0.0, "A1 +13:25 平倉成本")
go(30, 5.0, 0.0, X.SL_COST, 0.0, "A2 +停損價差")
go(30, 5.0, X.FC_COST, X.SL_COST, 0.0, "A3 +兩者（= A 的無滑價版）")
go(30, 5.0, X.FC_COST, X.SL_COST, 1.0, "A4 +進場滑價（= B）")
go(10 ** 9, 5.0, 0.0, 0.0, 0.0, "A5 舊設定但不限每日筆數")
