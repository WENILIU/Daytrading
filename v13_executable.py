"""The executable book: same signals, but every fill assumption replaced by a
measured one.

Measured inputs (all from the local 1-minute corpus on the orders this strategy
actually places; see v13_fillcost.py, v13_openk.py, v13_exitcost.py):

  entry slippage   cost as a function of PREDICTED participation. Predicted
                   participation = notional / (k * dv1), k = 0.1497 = the measured
                   median of (opening value / T-1 turnover). The curve is the
                   measured conditional mean E[cost | predicted participation],
                   which is the only version a live system can act on - actual
                   participation correlates with predicted at only r=0.20, so the
                   steeper curve measured against ACTUAL participation is not
                   something you can trade against.
  force close      +0.05% on force-closed trades, ~0.007% per trade overall. Left
                   in as a constant because it is a real, if tiny, cost.
  stop fill        ~0.015% per trade overall. Same.

The measured costs are taken at the close of the 09:00 bar, i.e. ~60s after the
open. RISK1 says the opening print only becomes readable 10-16s after 09:00:00, so
a real fill lands nearer 20s and the true cost is between 0.33x and 1.0x of the
measured curve. slip_scale spans that range; 1.0 is the stress case.

Everything else is the live book unchanged: 4.5M, whole lots, 100% exposure, 25%
per name, the 30-order/day cap, and the R9 sizing rule.

Usage: python v13_executable.py
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from v13_engine import run_backtest, stats, exit_of_legal, CAP0, COST
import v13_sizing as S

K_OPEN = 0.1497          # median opening value / T-1 dollar turnover
FC_COST = 0.000498       # 13:25 vs 13:30, per force-closed trade
SL_COST = 0.002053       # stop fill vs stop level, per stop-triggered trade

# E[cost | predicted participation], measured. Monotone by construction.
CURVE = [(0.0, -0.0002), (0.02, -0.0002), (0.05, 0.00038),
         (0.10, 0.00038), (0.20, 0.00242), (1e9, 0.00242)]

def slip_cost(part, scale):
    if not np.isfinite(part) or part <= 0:
        return 0.0
    for i in range(1, len(CURVE)):
        if part <= CURVE[i][0]:
            x0, y0 = CURVE[i - 1]; x1, y1 = CURVE[i]
            return (y0 + (y1 - y0) * (part - x0) / (x1 - x0)) * scale
    return CURVE[-1][1] * scale

CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
_, got, _ = run_backtest(capture=("2010-01-01", "2026-12-31"), capital=CAP0, **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
BASE = {k: v for k, v in S.R9.items() if k not in ("min_turnover_factor", "dv_cap", "dv_skip")}

def run(order_cap=30, slip_scale=1.0, cap_part=None, floor=None, exposure=1.0, label=""):
    rule = dict(BASE)
    if floor is not None:
        rule["min_turnover_factor"] = floor
    if cap_part is not None:
        rule["dv_cap"] = K_OPEN * cap_part
    rows = []; n_all = 0; capped = 0; gross_sum = 0.0; slip_sum = 0.0; parts = []
    for d, g in D.groupby("date"):
        g = g.sort_values("_rank"); rem = CAP0 * exposure; n_day = 0; yuan = 0.0
        for _, r in g.iterrows():
            if n_day >= order_cap:
                capped += 1; break
            pr = float(r["entry"]); code = str(r["stock"])
            dv1 = float(TO1.at[d, code]) if (code in TO1.columns and d in TO1.index) else np.nan
            n = S.lots_for(rule, float(r["_weight"]), pr, rem, dv1, capital=CAP0)
            if n <= 0:
                continue
            sh = n * 1000.0; notional = sh * pr
            pred = notional / (K_OPEN * dv1) if (np.isfinite(dv1) and dv1 > 0) else np.nan
            ex, slp, tpp, reason, gross = exit_of_legal(
                r["direction"], pr, float(r["day_high"]), float(r["day_low"]), float(r["day_close"]),
                float(r["lu"]), float(r["ld"]), float(r["tick"]), float(r["tp"]))
            if reason == "13:25 強制平倉":
                gross -= FC_COST
            elif reason.startswith("停損"):
                gross -= SL_COST
            sc = slip_cost(pred, slip_scale)
            gross -= 2 * COST + sc
            rem -= notional; yuan += notional * gross; n_day += 1; n_all += 1
            gross_sum += notional * gross; slip_sum += notional * sc
            if np.isfinite(pred):
                parts.append(pred)
        rows.append((d, yuan / CAP0))
    s = pd.Series([x[1] for x in rows], index=pd.to_datetime([x[0] for x in rows]))
    st = stats(s)
    P = np.array(parts) * 100 if parts else np.array([0.0])
    return st, s, dict(n=n_all, capped=capped, per_day=n_all / len(s),
                       gross=gross_sum, slip=slip_sum,
                       p50=np.percentile(P, 50), p90=np.percentile(P, 90), p99=np.percentile(P, 99))

if __name__ == "__main__":
    VARIANTS = [
        ("A 現行 f=5.0 無滑價",        dict(floor=5.0, slip_scale=0.0)),
        ("B 現行 f=5.0 +滑價(保守60s)", dict(floor=5.0, slip_scale=1.0)),
        ("C 無門檻 +滑價(保守60s)",     dict(slip_scale=1.0)),
        ("D 無門檻 +滑價(20s)",         dict(slip_scale=0.33)),
        ("E 參與率上限20% +滑價",       dict(cap_part=0.20, slip_scale=1.0)),
        ("F 參與率上限10% +滑價",       dict(cap_part=0.10, slip_scale=1.0)),
        ("G 參與率上限5% +滑價",        dict(cap_part=0.05, slip_scale=1.0)),
        ("H 無門檻 +滑價 +50筆/日",     dict(slip_scale=1.0, order_cap=50)),
        ("I 無門檻 +滑價 +不限筆",      dict(slip_scale=1.0, order_cap=10**9)),
        ("J 上限10% +滑價 +50筆/日",    dict(cap_part=0.10, slip_scale=1.0, order_cap=50)),
    ]
    print("%-30s %8s %8s %7s %6s %6s %8s %s" %
          ("variant", "CAGR", "MDD", "Sharpe", "筆/日", "觸頂日", "滑價合計", "預測參與率 p50/p90/p99"))
    res = {}
    for name, kw in VARIANTS:
        st, s, m = run(**kw)
        res[name] = (st, s)
        print("%-30s %7.1f%% %7.2f%% %7.2f %6.1f %6d %8s  %.2f%% / %.1f%% / %.1f%%" %
              (name, st["cagr"], st["mdd"], st["sharpe"], m["per_day"], m["capped"],
               "{:,.0f}".format(m["slip"]), m["p50"], m["p90"], m["p99"]))
    print()
    print("=== 逐年（滑價計入後）===")
    tbl = {k: v[1].groupby(v[1].index.year).apply(lambda x: ((1 + x).prod() - 1) * 100).round(1)
           for k, v in res.items()}
    print(pd.DataFrame(tbl).to_string())
