"""Answer the question the way it is actually asked: "I trade 4.5M, what do I get?"

Two conventions have been circulating in this project and they are not
interchangeable, so both are reported here instead of one:

  固定450萬（獲利出金）- every day the book is 4.5M again. The honest statistic is
                        the ARITHMETIC annual P&L on that base, and the drawdown is
                        measured on the TWD equity curve. Compounding a return series
                        whose positions were sized on a fixed base is not a real
                        account: it assumes the sizes grow with equity while paying
                        for sizes that do not.
  照淨值複利          - a real account that keeps its profits. Positions are sized
                        off current equity, so growth, participation and the
                        measured fill cost all move together. This is where the
                        strategy's capacity shows up by itself.

Both include the measured costs: entry slippage at the ~20s fill RISK1 implies, the
stop-trigger gap at its end-of-minute bound, the 13:25 vs 13:30 close difference,
and 1.8-zhe commission plus day-trade tax.

Usage: python v13_realbook.py
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
RSCFG = (-0.006, 0.30, -0.012, 0.12)


def rs_of(cdd):
    if cdd < RSCFG[0]:
        return RSCFG[1]
    if cdd < RSCFG[2]:
        return RSCFG[3]
    return 1.0


def simulate(cap_x=None, floor=None, compound=True):
    rule = dict(BASE)
    if floor is not None:
        rule["min_turnover_factor"] = floor
    if cap_x is not None:
        rule["dv_cap"] = K_OPEN * cap_x
    eq = float(CAP0); peak = float(CAP0); pnl_twd = 0.0; pnl_peak = 0.0
    rows = []; n_all = 0; parts = []
    for d, g in D.groupby("date"):
        base = eq if compound else float(CAP0)
        cdd = ((eq - peak) / peak) if compound else (pnl_twd - pnl_peak) / CAP0
        rs = rs_of(cdd)
        g = g.sort_values("_rank"); rem = base; n_day = 0; yuan = 0.0
        for _, r in g.iterrows():
            if n_day >= 30:
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
            if reason == "13:25 強制平倉":
                gross -= FC_COST
            if reason.startswith("停損"):
                gross -= SL_COST
            pred = notional / (K_OPEN * dv1) if (np.isfinite(dv1) and dv1 > 0) else np.nan
            gross -= 2 * COST + slip_cost(pred, 0.33)
            if np.isfinite(pred):
                parts.append(pred)
            rem -= notional; yuan += notional * gross; n_day += 1; n_all += 1
        if compound:
            ret = yuan / eq; eq *= 1 + ret; peak = max(peak, eq)
        else:
            ret = yuan / CAP0
            pnl_twd += yuan; pnl_peak = max(pnl_peak, pnl_twd)
        rows.append((d, ret, yuan))
    idx = pd.to_datetime([x[0] for x in rows])
    r = pd.Series([x[1] for x in rows], index=idx)
    y = pd.Series([x[2] for x in rows], index=idx)
    P = np.array(parts) * 100 if parts else np.array([0.0])
    ann = y.groupby(y.index.year).sum() / CAP0 * 100
    cum = y.cumsum()
    mdd_twd = ((cum - cum.cummax()) / CAP0).min() * 100
    st = stats(r)
    return dict(ann=ann, mdd_twd=mdd_twd, total_twd=y.sum(), per_day=n_all / len(r),
                p50=np.percentile(P, 50), p90=np.percentile(P, 90),
                cagr=st["cagr"], mdd=st["mdd"], sharpe=st["sharpe"],
                final_eq=eq if compound else CAP0 + y.sum())


CASES = [
    ("現行設定（f=5.0 門檻）", dict(floor=5.0)),
    ("拿掉流動性門檻", dict()),
    ("拿掉門檻 + 單量≤開盤可成交額25%", dict(cap_x=0.25)),
    ("拿掉門檻 + 單量≤10%", dict(cap_x=0.10)),
]
for name, kw in CASES:
    fx = simulate(compound=False, **kw)
    cp = simulate(compound=True, **kw)
    print("=" * 96)
    print(name)
    print("  【固定450萬、獲利出金】每年實際損益%（算术，不複利）")
    print("    " + "  ".join("%d:%+.0f%%" % (k, v) for k, v in fx["ann"].items()))
    print("    12.5 年合計 %s 元   最大回撤（占450萬）%.2f%%   筆/日 %.1f" %
          ("{:,.0f}".format(fx["total_twd"]), fx["mdd_twd"], fx["per_day"]))
    print("    平均年報酬 %+.1f%%   最差年 %+.1f%%" % (fx["ann"].mean(), fx["ann"].min()))
    print("  【照淨值複利】CAGR %.1f%% / MDD %.2f%% / Sharpe %.2f  最終淨值 %s" %
          (cp["cagr"], cp["mdd"], cp["sharpe"], "{:,.0f}".format(cp["final_eq"])))
    print("    預測參與率 p50 %.1f%% p90 %.1f%%  <- 超過 100%% 代表單比整場開盤還大，填不進去" %
          (cp["p50"], cp["p90"]))
