"""The live book, sized the way a live account actually sizes.

Found while reconciling the two books: the engine sizes each day off CURRENT equity
(`caps["A"] = eq`) and divides the day's PnL by that same equity, so its compounding
is internally consistent. Every replay of the live rules that reproduced the
published 121.9% sized off a FIXED 4,500,000 and then compounded the result. Those
are not the same book. Sizing off a fixed base while compounding the returns
assumes the position sizes grow with equity without paying for the consequences -
and the consequence here is measurable, because bigger positions mean a bigger share
of the opening tape, which is exactly the cost v13_fillcost.py measured.

A live account sizes off whatever it currently has. That is what this does:

    lots = int(w * equity / (price * 1000))
    day return = PnL / equity
    equity *= (1 + day return)

so growth, position size, participation, and the measured fill cost all move
together. The fixed-base number is kept as a validation row only.

Usage: python v13_livebook.py
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


def rs_of(cdd, cfg):
    if cfg is None:
        return 1.0
    t1, s1, t2, s2 = cfg
    if cdd < t1:
        return s1
    if cdd < t2:
        return s2
    return 1.0


def run(floor=5.0, order_cap=30, slip_scale=0.33, stop_scale=1.0, fc=True,
        rscfg=(-0.006, 0.30, -0.012, 0.12), fixed_base=False, label=""):
    rule = dict(BASE)
    if floor is not None:
        rule["min_turnover_factor"] = floor
    eq = float(CAP0); peak = float(CAP0)
    rows = []; n_all = 0; parts = []
    for d, g in D.groupby("date"):
        base = float(CAP0) if fixed_base else eq
        cdd = (eq - peak) / peak
        rs = rs_of(cdd, rscfg)
        g = g.sort_values("_rank"); rem = base; n_day = 0; yuan = 0.0
        for _, r in g.iterrows():
            if n_day >= order_cap:
                break
            pr = float(r["entry"]); code = str(r["stock"])
            w = float(r["_weight"]) / (float(r["_rs"]) or 1.0) * rs
            dv1 = float(TO1.at[d, code]) if (code in TO1.columns and d in TO1.index) else np.nan
            n = S.lots_for(rule, w, pr, rem, dv1, capital=base)
            if n <= 0:
                continue
            sh = n * 1000.0; notional = sh * pr
            ex, slp, tpp, reason, gross = exit_of_legal(
                r["direction"], pr, float(r["day_high"]), float(r["day_low"]), float(r["day_close"]),
                float(r["lu"]), float(r["ld"]), float(r["tick"]), float(r["tp"]))
            if fc and reason == "13:25 強制平倉":
                gross -= FC_COST
            if reason.startswith("停損"):
                gross -= SL_COST * stop_scale
            pred = notional / (K_OPEN * dv1) if (np.isfinite(dv1) and dv1 > 0) else np.nan
            gross -= 2 * COST + slip_cost(pred, slip_scale)
            if np.isfinite(pred):
                parts.append(pred)
            rem -= notional; yuan += notional * gross; n_day += 1; n_all += 1
        ret = yuan / base
        eq *= 1 + ret; peak = max(peak, eq)
        rows.append((d, ret))
    s = pd.Series([x[1] for x in rows], index=pd.to_datetime([x[0] for x in rows]))
    st = stats(s)
    P = np.array(parts) * 100 if parts else np.array([0.0])
    return st, s, dict(per_day=n_all / len(s), final=eq,
                       p50=np.percentile(P, 50), p90=np.percentile(P, 90), p99=np.percentile(P, 99))


V = [
    ("0 驗證舊口徑（固定450萬、無新成本）", dict(floor=5.0, fixed_base=True, slip_scale=0.0, stop_scale=0.0, fc=False)),
    ("1 正確口徑 + 現行 f=5.0 門檻、無新成本", dict(floor=5.0, slip_scale=0.0, stop_scale=0.0, fc=False)),
    ("2 同上 + 全部實測成本", dict(floor=5.0)),
    ("3 拿掉流動性門檻 + 全部實測成本", dict(floor=None)),
    ("4 3 + 停損價差取上界（最保守）", dict(floor=None, stop_scale=1.0, slip_scale=1.0)),
    ("5 3 + 淨值回撤控制關掉", dict(floor=None, rscfg=None)),
    ("6 3 + 放寬 -1.5%→50% / -3%→15%", dict(floor=None, rscfg=(-0.015, 0.5, -0.03, 0.15))),
]
print("%-40s %8s %8s %7s %6s %12s %s" %
      ("variant", "CAGR", "MDD", "Sharpe", "筆/日", "最終淨值", "預測參與率 p50/p90/p99"))
res = {}
for name, kw in V:
    st, s, m = run(**kw)
    res[name] = (st, s)
    print("%-40s %7.1f%% %7.2f%% %7.2f %6.1f %12s  %.2f%% / %.1f%% / %.1f%%" %
          (name, st["cagr"], st["mdd"], st["sharpe"], m["per_day"], "{:,.0f}".format(m["final"]),
           m["p50"], m["p90"], m["p99"]))
print()
print("=== 逐年 ===")
tbl = {k.split()[0]: v[1].groupby(v[1].index.year).apply(lambda x: ((1 + x).prod() - 1) * 100).round(1)
       for k, v in res.items()}
print(pd.DataFrame(tbl).to_string())
