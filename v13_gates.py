"""The one corner left: buy more exposure and pay for it with a tighter drawdown gate.

scale raises exposure and MDD together. The drawdown gate is the only knob that
reduces MDD without reducing edge on the days that are working, so the pair
(scale up, gate tighter) is the last combination that could beat the current
operating point at the same -5%. Every gate here is the same two-step form live
already uses, just with different thresholds - all computable at 09:00 from the
book's own equity file.

Usage: python v13_gates.py
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
FCD = pd.DataFrame(pd.read_pickle("_fcd_panel.pkl")); FCD.index = pd.to_datetime(FCD.index)
DTV = pd.DataFrame(pd.read_pickle("_dtvol_panel.pkl")); DTV.index = pd.to_datetime(DTV.index)
FCD.columns = [str(c) for c in FCD.columns]; DTV.columns = [str(c) for c in DTV.columns]
FCD = FCD.reindex(index=sorted(D["date"].unique()), columns=sorted(D["stock"].unique()))
DTV = DTV.reindex(index=sorted(D["date"].unique()), columns=sorted(D["stock"].unique()))
fcd = FCD.fillna(False).astype(bool).values; dtv = DTV.values
dpos = {d: i for i, d in enumerate(FCD.index.values)}
fc_pos = {c: j for j, c in enumerate(FCD.columns)}; dc_pos = {c: j for j, c in enumerate(DTV.columns)}
ri = np.array([dpos[d] for d in D["date"].values])
cj = D["stock"].map(fc_pos).fillna(-1).astype(int).values
dj = D["stock"].map(dc_pos).fillna(-1).astype(int).values
D["blocked"] = ((cj >= 0) & fcd[ri, np.clip(cj, 0, fcd.shape[1] - 1)]) | \
               ((dj >= 0) & (DTV.values[ri, np.clip(dj, 0, dtv.shape[1] - 1)] == 0))
print("blocked %d/%d" % (D["blocked"].sum(), len(D)), flush=True)

GATES = {"現行 -0.6%->30%/-1.2%->12%": (-0.006, 0.30, -0.012, 0.12),
         "-0.4%->25%/-0.8%->10%": (-0.004, 0.25, -0.008, 0.10),
         "-0.3%->20%/-0.6%->08%": (-0.003, 0.20, -0.006, 0.08),
         "-0.2%->15%/-0.4%->05%": (-0.002, 0.15, -0.004, 0.05)}


def simulate(compound, scale=1.0, cap_pct=0.25, gate=(-0.006, 0.30, -0.012, 0.12)):
    rule = dict(BASE); rule["dv_cap"] = K_OPEN * 0.25
    rule["scale"] = scale; rule["cap_pct"] = cap_pct
    t1, s1, t2, s2 = gate
    eq = float(CAP0); peak = float(CAP0); pnl = 0.0; pnl_peak = 0.0
    rows = []; n_all = 0; expo = []
    for d, g in D.groupby("date"):
        base = eq if compound else float(CAP0)
        cdd = ((eq - peak) / peak) if compound else (pnl - pnl_peak) / CAP0
        rs = s1 if cdd < t1 else (s2 if cdd < t2 else 1.0)
        g = g[~g["blocked"]].sort_values("_rank")
        rem = base; n_day = 0; yuan = 0.0
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
            rem -= notional; yuan += notional * gross; n_day += 1; n_all += 1
        expo.append((base - rem) / base)
        if compound:
            ret = yuan / eq; eq *= 1 + ret; peak = max(peak, eq)
        else:
            ret = yuan / CAP0; pnl += yuan; pnl_peak = max(pnl_peak, pnl)
        rows.append((d, ret, yuan))
    idx2 = pd.to_datetime([x[0] for x in rows])
    s = pd.Series([x[1] for x in rows], index=idx2)
    y = pd.Series([x[2] for x in rows], index=idx2)
    ann = y.groupby(y.index.year).sum() / CAP0 * 100
    cum = y.cumsum()
    return dict(avg=ann.mean(), worst=ann.min(), total=y.sum(), ann=ann,
                mdd_twd=((cum - cum.cummax()) / CAP0).min() * 100,
                per_day=n_all / len(s), expo=np.percentile(np.array(expo), 50),
                st=stats(s))


HDR = "%-34s %8s %8s %9s %11s | %8s %8s | %6s %6s"
print()
print("450萬、整張、零融資、單量<=開盤可成交額25%%、成本全含、可執行性已過濾")
print(HDR % ("變體", "年均%", "最差年%", "MDD占本%", "12.5年合計", "複利CAGR", "複利MDD", "筆/日", "曝險%"))
best = None
for sc in (1.0, 1.5, 2.0):
    for gn, gt in GATES.items():
        f = simulate(False, sc, 0.25, gt); c = simulate(True, sc, 0.25, gt)
        print(HDR % ("scale%.1f  %s" % (sc, gn), f["avg"], f["worst"], f["mdd_twd"],
                     "{:,.0f}".format(f["total"]), c["st"]["cagr"], c["st"]["mdd"],
                     f["per_day"], f["expo"] * 100))
        if f["mdd_twd"] >= -5.0 and (best is None or f["avg"] > best[0]):
            best = (f["avg"], f["mdd_twd"], sc, gn, f, c)
    print()
if best:
    print("MDD 不劣於 -5%% 的最高年均：scale%.1f、%s -> 年均 %.1f%% / MDD %.2f%% / 合計 %s 元" % (
        best[2], best[3], best[0], best[1], "{:,.0f}".format(best[4]["total"])))
    print("  逐年：", {int(k): round(v, 1) for k, v in best[4]["ann"].items()})
