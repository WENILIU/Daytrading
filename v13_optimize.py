"""Optimise the executable book, not the engine's book.

Two corrections to how the live book was being simulated, then a scan.

1. The equity drawdown control. The captured design weight already has the engine's
   `rs` multiplied in, and that `rs` is computed from the ENGINE's equity path. The
   live book is a different path - different fills, different sizes - so replaying
   the engine's rs against it is not the live rule. Here the design weight is
   divided back out by the recorded `_rs` and the control is recomputed from the
   live book's own equity, which is what the script would actually do at 09:00.

2. The participation gate. Measured cost 24-45pp of CAGR while MDD gets WORSE
   (v13_executable.py C vs G). It is a return tax, not a risk control, so it comes
   out and the scan searches the real frontier instead.

Costs are the measured ones. slip_scale 0.33 is the ~20s fill RISK1 implies, 1.0 is
the ~60s bound; stop-gap 1.0 is the measured end-of-minute bound and 0.0 is an
instant fill at the stop level. The honest answer is the range between them.

Usage: python v13_optimize.py
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from v13_engine import run_backtest, stats, exit_of_legal, CAP0, COST
import v13_sizing as S
from v13_executable import slip_cost, K_OPEN, FC_COST, SL_COST

CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
_, got, _ = run_backtest(capture=("2014-01-01", "2026-12-31"), capital=CAP0, **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
BASE = {k: v for k, v in S.R9.items() if k not in ("min_turnover_factor", "dv_cap", "dv_skip")}

# (t1, s1, t2, s2): equity dd < t1 -> scale s1; < t2 -> scale s2 (t2 more negative)
RS = {
    "引擎現行 -0.6%→30% / -1.2%→12%": (-0.006, 0.30, -0.012, 0.12),
    "放寬 -1.5%→50% / -3.0%→15%":     (-0.015, 0.50, -0.030, 0.15),
    "放寬 -2.0%→60% / -4.0%→20%":     (-0.020, 0.60, -0.040, 0.20),
    "放寬 -1.0%→40% / -2.0%→10%":     (-0.010, 0.40, -0.020, 0.10),
    "關掉":                            (None, 1.0, None, 1.0),
}


def rs_of(cdd, cfg):
    t1, s1, t2, s2 = cfg
    if t1 is not None and cdd < t1:
        return s1
    if t2 is not None and cdd < t2:
        return s2
    return 1.0


def run(rscfg, slip_scale=0.33, stop_scale=1.0, cap_pct=0.25, order_cap=30, floor=None):
    rule = dict(BASE)
    rule["cap_pct"] = cap_pct
    if floor is not None:
        rule["min_turnover_factor"] = floor
    eq = CAP0; peak = CAP0
    rows = []; n_all = 0
    for d, g in D.groupby("date"):
        cdd = (eq - peak) / peak
        rs = rs_of(cdd, rscfg)
        g = g.sort_values("_rank"); rem = CAP0; n_day = 0; yuan = 0.0
        for _, r in g.iterrows():
            if n_day >= order_cap:
                break
            pr = float(r["entry"]); code = str(r["stock"])
            rs0 = float(r["_rs"]) or 1.0
            w = float(r["_weight"]) / rs0 * rs
            dv1 = float(TO1.at[d, code]) if (code in TO1.columns and d in TO1.index) else np.nan
            n = S.lots_for(rule, w, pr, rem, dv1, capital=CAP0)
            if n <= 0:
                continue
            sh = n * 1000.0; notional = sh * pr
            ex, slp, tpp, reason, gross = exit_of_legal(
                r["direction"], pr, float(r["day_high"]), float(r["day_low"]), float(r["day_close"]),
                float(r["lu"]), float(r["ld"]), float(r["tick"]), float(r["tp"]))
            if reason == "13:25 強制平倉":
                gross -= FC_COST
            elif reason.startswith("停損"):
                gross -= SL_COST * stop_scale
            gross -= 2 * COST + slip_cost(
                notional / (K_OPEN * dv1) if (np.isfinite(dv1) and dv1 > 0) else np.nan, slip_scale)
            rem -= notional; yuan += notional * gross; n_day += 1; n_all += 1
        eq += yuan; peak = max(peak, eq)
        rows.append((d, yuan / CAP0))
    s = pd.Series([x[1] for x in rows], index=pd.to_datetime([x[0] for x in rows]))
    return stats(s), s, n_all / len(s)


print("成本口徑：進場滑價 0.33x（~20秒，RISK1 實測）、停損價差 1.0x（分鐘末，上界）")
print("%-38s %8s %8s %7s %6s" % ("淨值回撤控制", "CAGR", "MDD", "Sharpe", "筆/日"))
res = {}
for name, cfg in RS.items():
    st, s, pd_ = run(cfg)
    res[name] = (st, s)
    print("%-38s %7.1f%% %7.2f%% %7.2f %6.1f" % (name, st["cagr"], st["mdd"], st["sharpe"], pd_))
print()
best = max(res.items(), key=lambda kv: kv[1][0]["cagr"] if kv[1][0]["mdd"] >= -5.0 else -999)
print("在 MDD 不劣於 -5%% 的前提下最佳：%s -> CAGR %.1f%% MDD %.2f%%" %
      (best[0], best[1][0]["cagr"], best[1][0]["mdd"]))
print()
print("=== 逐年（該設定）===")
print((best[1][1].groupby(best[1][1].index.year).apply(lambda x: ((1 + x).prod() - 1) * 100)).round(1).to_string())
