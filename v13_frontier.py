"""The real frontier: highest CAGR at MDD no worse than -5%, with every fill
required to be fillable.

Correct sizing (positions off current equity) plus the measured fill costs, then
two knobs that trade against each other:

  fillable cap   - cap the order at X of the predicted opening value. Below this
                   the measured fill cost is near zero; above it the order is not
                   something the opening tape can absorb. Without this knob the
                   backtest happily grows into a book that trades more than the
                   whole market opens with, and the later years are fiction.
  drawdown gate  - scale new positions when the book is off its peak.

Everything else is the live book. The liquidity gate is off: measured, it costs
84pp of CAGR and makes MDD worse (v13_livebook.py 1 vs 3).

Usage: python v13_frontier.py
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

RS = {"現行 -0.6%→30%/-1.2%→12%": (-0.006, 0.30, -0.012, 0.12),
      "-1.0%→45%/-2.0%→12%": (-0.010, 0.45, -0.020, 0.12),
      "-1.5%→50%/-3.0%→15%": (-0.015, 0.50, -0.030, 0.15),
      "-2.5%→60%/-5.0%→20%": (-0.025, 0.60, -0.050, 0.20),
      "關掉": None}
CAPS = {"10%": 0.10, "25%": 0.25, "50%": 0.50, "100%": 1.00, "不限": None}


def rs_of(cdd, cfg):
    if cfg is None:
        return 1.0
    t1, s1, t2, s2 = cfg
    if cdd < t1:
        return s1
    if cdd < t2:
        return s2
    return 1.0


def run(cap_x, rscfg, slip_scale=0.33, stop_scale=1.0):
    rule = dict(BASE)
    if cap_x is not None:
        rule["dv_cap"] = K_OPEN * cap_x
    eq = float(CAP0); peak = float(CAP0)
    rows = []; n_all = 0; parts = []; capped = 0
    for d, g in D.groupby("date"):
        cdd = (eq - peak) / peak
        rs = rs_of(cdd, rscfg)
        g = g.sort_values("_rank"); rem = eq; n_day = 0; yuan = 0.0
        for _, r in g.iterrows():
            if n_day >= 30:
                break
            pr = float(r["entry"]); code = str(r["stock"])
            w = float(r["_weight"]) / (float(r["_rs"]) or 1.0) * rs
            dv1 = float(TO1.at[d, code]) if (code in TO1.columns and d in TO1.index) else np.nan
            n = S.lots_for(rule, w, pr, rem, dv1, capital=eq)
            if n <= 0:
                continue
            sh = n * 1000.0; notional = sh * pr
            ex, slp, tpp, reason, gross = exit_of_legal(
                r["direction"], pr, float(r["day_high"]), float(r["day_low"]), float(r["day_close"]),
                float(r["lu"]), float(r["ld"]), float(r["tick"]), float(r["tp"]))
            if reason == "13:25 強制平倉":
                gross -= FC_COST
            if reason.startswith("停損"):
                gross -= SL_COST * stop_scale
            pred = notional / (K_OPEN * dv1) if (np.isfinite(dv1) and dv1 > 0) else np.nan
            gross -= 2 * COST + slip_cost(pred, slip_scale)
            if np.isfinite(pred):
                parts.append(pred)
            if np.isfinite(pred) and pred > 0.5:
                capped += 1
            rem -= notional; yuan += notional * gross; n_day += 1; n_all += 1
        ret = yuan / eq
        eq *= 1 + ret; peak = max(peak, eq)
        rows.append((d, ret))
    s = pd.Series([x[1] for x in rows], index=pd.to_datetime([x[0] for x in rows]))
    st = stats(s)
    P = np.array(parts) * 100 if parts else np.array([0.0])
    return st, s, dict(per_day=n_all / len(s), final=eq, over50=capped,
                       p50=np.percentile(P, 50), p90=np.percentile(P, 90))


print("成本：進場滑價 0.33x（~20秒）、停損價差 1.0x（分鐘末上界）、13:25 平倉差、手續費 1.8 折")
print("部位照目前淨值計算。左欄=單量上限（佔該股開盤可成交額），上欄=淨值回撤控制")
hdr = "%-10s" % "單量上限" + "".join("%26s" % k for k in RS)
print(hdr)
best = None
for cn, cx in CAPS.items():
    line = "%-10s" % cn
    for rn, rc in RS.items():
        st, s, m = run(cx, rc)
        tag = "%7.1f%% / %6.2f%%" % (st["cagr"], st["mdd"])
        line += "%26s" % tag
        if st["mdd"] >= -5.0 and (best is None or st["cagr"] > best[0]):
            best = (st["cagr"], st["mdd"], cn, rn, s, m)
    print(line)
print()
if best:
    print("MDD 不劣於 -5%% 的最高 CAGR：單量上限 %s、回撤控制 %s -> CAGR %.1f%% / MDD %.2f%%" %
          (best[2], best[3], best[0], best[1]))
    m = best[5]
    print("  筆/日 %.1f  最終淨值 %s  預測參與率 p50 %.1f%% p90 %.1f%%  超過50%%的單 %d 筆" %
          (m["per_day"], "{:,.0f}".format(m["final"]), m["p50"], m["p90"], m["over50"]))
    s = best[4]
    print("  逐年：")
    print(s.groupby(s.index.year).apply(lambda x: ((1 + x).prod() - 1) * 100).round(1).to_string())
