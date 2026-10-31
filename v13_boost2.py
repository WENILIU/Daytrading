"""Push the book harder without breaking a real 4.5M account.

Two things were measured first, and both shape this script:

  rank does not carry edge - top-1 averages +0.65% vs +0.43% for everything, and
  its win rate is LOWER (45.7% vs 55.9%). "Take only the top K" is not a lever.
  weight does carry edge - the top weight quintile averages +1.41%, the bottom
  three +0.05%. The model's own sizing already encodes the ranking; the raw
  ordering used to walk the list does not.

So the lever is selectivity on weight plus filling the cash that selectivity
frees up. With zero margin the book can never exceed 100%, so annual P&L is
exposure x edge-per-TWD: raising the weight floor buys edge, and raising the
per-name cap is what converts the freed cash back into exposure.

Also measured here for the first time in the backtest: the two executability
panels live has used since 2026-10-28 but the signal pool never did - 全額交割
(cannot day trade at all) and zero per-stock day-trade volume. If a signal is
here that the exchange says nobody day trades, the backtest was trading
something live would skip.

Both accounting conventions are reported because they answer different questions:
  FIXED    - the account stays at 4.5M, profits withdrawn. Arithmetic annual P&L
             on that base, drawdown in TWD against that base. This is what
             "I trade 4.5M" means, and capacity does not bind here.
  COMPOUND - the account keeps its profits, positions sized off current equity,
             so participation and measured fill cost rise together. This is where
             200% CAGR either exists or does not.

Costs in both: entry slippage on predicted participation at the ~20s fill RISK1
implies, stop-trigger gap at its end-of-minute bound, 13:25 vs 13:30 close,
commission 1.8 zhe plus day-trade tax. Orders capped at 25% of the predicted
opening fillable amount so every fill stays fillable.

Usage: python v13_boost2.py
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from v13_engine import run_backtest, stats, exit_of_legal, CAP0, COST
import v13_sizing as S
from v13_executable import slip_cost, K_OPEN, FC_COST, SL_COST

CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
_, got, _ = run_backtest(capture=("2014-01-01", "2026-12-31"), capital=CAP0, **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)
D["date"] = pd.to_datetime(D["date"])
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
BASE = {k: v for k, v in S.R9.items() if k not in ("min_turnover_factor", "dv_cap", "dv_skip")}
RSCFG = (-0.006, 0.30, -0.012, 0.12)
CAPX = 0.25

# executability: the exchange's own day-trade volume, and the full-settlement list
FCD = pd.DataFrame(pd.read_pickle("_fcd_panel.pkl")); FCD.index = pd.to_datetime(FCD.index)
DTV = pd.DataFrame(pd.read_pickle("_dtvol_panel.pkl")); DTV.index = pd.to_datetime(DTV.index)
FCD.columns = [str(c) for c in FCD.columns]; DTV.columns = [str(c) for c in DTV.columns]
FCD = FCD.reindex(index=D["date"].unique(), columns=D["stock"].unique())
DTV = DTV.reindex(index=D["date"].unique(), columns=D["stock"].unique())
fcd = FCD.fillna(False).astype(bool).values
dtv = DTV.values
idx = {(d, s): i for i, (d, s) in enumerate(zip(D["date"], D["stock"]))}
blocked = np.zeros(len(D), bool)
fc_pos = {c: j for j, c in enumerate(FCD.columns)}
dc_pos = {c: j for j, c in enumerate(DTV.columns)}
ri = np.clip(np.searchsorted(FCD.index.values, D["date"].values), 0, fcd.shape[0] - 1)
di = np.clip(np.searchsorted(DTV.index.values, D["date"].values), 0, dtv.shape[0] - 1)
cj = D["stock"].map(fc_pos).fillna(-1).astype(int).values
dj = D["stock"].map(dc_pos).fillna(-1).astype(int).values
m1 = (cj >= 0) & fcd[ri, np.clip(cj, 0, fcd.shape[1] - 1)]
m2 = (dj >= 0) & (dtv[di, np.clip(dj, 0, dtv.shape[1] - 1)] == 0)
blocked = m1 | m2
N_FCD = int(m1.sum()); N_DTV = int((m2 & ~m1).sum())
D["blocked"] = blocked
print("可執行性面板：訊號 %d 筆中被擋 %d 筆（全額交割 %d、零當沖量 %d），面板停在 %s / %s" % (
    len(D), int(blocked.sum()), N_FCD, N_DTV,
    FCD.index.max().date(), DTV.index.max().date()), flush=True)


def rs_of(cdd):
    if cdd < RSCFG[0]:
        return RSCFG[1]
    if cdd < RSCFG[2]:
        return RSCFG[3]
    return 1.0


def simulate(compound, wmin=0.0, cap_pct=0.25, scale=1.0, exec_filter=False):
    rule = dict(BASE); rule["dv_cap"] = K_OPEN * CAPX
    rule["scale"] = scale; rule["cap_pct"] = cap_pct
    eq = float(CAP0); peak = float(CAP0); pnl = 0.0; pnl_peak = 0.0
    rows = []; n_all = 0; parts = []; expo = []; breadth = []
    for d, g in D.groupby("date"):
        base = eq if compound else float(CAP0)
        cdd = ((eq - peak) / peak) if compound else (pnl - pnl_peak) / CAP0
        rs = rs_of(cdd)
        if exec_filter:
            g = g[~g["blocked"]]
        if wmin > 0:
            g = g[(g["_weight"] / g["_rs"].replace(0, np.nan)) >= wmin]
        g = g.sort_values("_rank"); rem = base; n_day = 0; yuan = 0.0
        breadth.append(len(g))
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
        expo.append((base - rem) / base)
        if compound:
            ret = yuan / eq; eq *= 1 + ret; peak = max(peak, eq)
        else:
            ret = yuan / CAP0; pnl += yuan; pnl_peak = max(pnl_peak, pnl)
        rows.append((d, ret, yuan))
    idx2 = pd.to_datetime([x[0] for x in rows])
    s = pd.Series([x[1] for x in rows], index=idx2)
    y = pd.Series([x[2] for x in rows], index=idx2)
    P = np.array(parts) * 100 if parts else np.array([0.0])
    E = np.array(expo); B = np.array(breadth)
    ann = y.groupby(y.index.year).sum() / CAP0 * 100
    cum = y.cumsum()
    return dict(ann=ann, avg=ann.mean(), worst=ann.min(), total=y.sum(),
                mdd_twd=((cum - cum.cummax()) / CAP0).min() * 100,
                per_day=n_all / len(s), final=eq if compound else CAP0 + y.sum(),
                p50=np.percentile(P, 50), p90=np.percentile(P, 90),
                expo=np.percentile(E, 50), breadth=np.percentile(B, 50),
                per_day_fixed=n_all / len(s), st=stats(s))


HDR = "%-30s %8s %8s %9s %10s | %8s %8s | %6s %6s %6s"
print()
print("成本全含 | 單量上限=開盤可成交額25%% | 零融資(曝險<=100%%) | 回撤控制 -0.6%%->30%%/-1.2%%->12%%")
print(HDR % ("變體", "固定年均%", "最差年%", "MDD占本%", "合計(元)", "複利CAGR", "複利MDD", "筆/日", "曝險%", "廣度"))
print("筆/日 = 450萬帳戶實際要下的單數；曝險% = 中位日投入占淨值比例（零融資上限100%）")


def show(label, **kw):
    f = simulate(compound=False, **kw); c = simulate(compound=True, **kw)
    print(HDR % (label, f["avg"], f["worst"], f["mdd_twd"], "{:,.0f}".format(f["total"]),
                 c["st"]["cagr"], c["st"]["mdd"], f["per_day_fixed"], f["expo"] * 100, f["breadth"]))
    return f, c


show("基準 + 可執行性過濾", exec_filter=True)
print()
for sc in (1.5, 2.0, 3.0, 5.0):
    for cp in (0.25, 0.35):
        show("scale%.1f cap%d%%" % (sc, int(cp * 100)),
             scale=sc, cap_pct=cp, exec_filter=True)
    print()
for wm in (0.05, 0.10):
    for sc in (2.0, 3.0):
        show("w>=%.2f scale%.1f cap35%%" % (wm, sc),
             wmin=wm, scale=sc, cap_pct=0.35, exec_filter=True)
    print()
