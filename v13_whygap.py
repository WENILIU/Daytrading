"""Why the published +198.8%/yr and the current +87.4%/yr are not the same number.

One run per removed assumption, everything else identical (4.5M reset each year,
whole lots, zero margin, 2014+). This is the ladder from the published table down
to what a real account would have made, with each rung measured rather than
asserted.

Usage: python v13_whygap.py
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from v13_engine import run_backtest, exit_of_legal, CAP0, COST
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
dp = {d: i for i, d in enumerate(FCD.index.values)}
fp = {c: j for j, c in enumerate(FCD.columns)}; gp = {c: j for j, c in enumerate(DTV.columns)}
ri = np.array([dp[d] for d in D["date"].values])
cj = D["stock"].map(fp).fillna(-1).astype(int).values
gj = D["stock"].map(gp).fillna(-1).astype(int).values
D["blocked"] = ((cj >= 0) & fcd[ri, np.clip(cj, 0, fcd.shape[1] - 1)]) | \
               ((gj >= 0) & (dtv[ri, np.clip(gj, 0, dtv.shape[1] - 1)] == 0))
RSCFG = (-0.006, 0.30, -0.012, 0.12)


def rs_of(c):
    return RSCFG[1] if c < RSCFG[0] else (RSCFG[3] if c < RSCFG[2] else 1.0)


def run(gate=True, exec_f=True, fc=True, sl=True, slip=True):
    rule = dict(BASE)
    if gate:
        rule["min_turnover_factor"] = 5.0
    else:
        rule["dv_cap"] = K_OPEN * 0.25
    eq = float(CAP0); peak = float(CAP0); pnl = 0.0; pnl_peak = 0.0
    rows = []; n_all = 0
    for d, g in D.groupby("date"):
        cdd = (pnl - pnl_peak) / CAP0
        rs = rs_of(cdd)
        if exec_f:
            g = g[~g["blocked"]]
        g = g.sort_values("_rank"); rem = CAP0; n_day = 0; yuan = 0.0
        for _, r in g.iterrows():
            if n_day >= 30:
                break
            pr = float(r["entry"]); code = str(r["stock"])
            w = float(r["_weight"]) / (float(r["_rs"]) or 1.0) * rs
            dv1 = float(TO1.at[d, code]) if (code in TO1.columns and d in TO1.index) else np.nan
            n = S.lots_for(rule, w, pr, rem, dv1, capital=CAP0)
            if n <= 0:
                continue
            notional = n * 1000.0 * pr
            ex, slp, tpp, reason, gross = exit_of_legal(
                r["direction"], pr, float(r["day_high"]), float(r["day_low"]), float(r["day_close"]),
                float(r["lu"]), float(r["ld"]), float(r["tick"]), float(r["tp"]))
            if reason == "13:25 強制平倉" and fc:
                gross -= FC_COST
            if reason.startswith("停損") and sl:
                gross -= SL_COST
            pred = notional / (K_OPEN * dv1) if (np.isfinite(dv1) and dv1 > 0) else np.nan
            gross -= 2 * COST
            if slip:
                gross -= slip_cost(pred, 0.33)
            rem -= notional; yuan += notional * gross; n_day += 1; n_all += 1
        pnl += yuan; pnl_peak = max(pnl_peak, pnl)
        rows.append((d, yuan))
    y = pd.Series([x[1] for x in rows], index=pd.to_datetime([x[0] for x in rows]))
    ann = y.groupby(y.index.year).sum() / CAP0 * 100
    cum = y.cumsum()
    return dict(avg=ann.mean(), worst=ann.min(), total=y.sum(),
                mdd=((cum - cum.cummax()) / CAP0).min() * 100, per_day=n_all / len(y))


print("450萬每年重設、整張、零融資、2014+。每一行只多拿掉一個假設。")
print("%-46s %9s %9s %10s %9s %7s" % ("情境", "年均%", "最差年%", "MDD占本%", "12.5年合計", "筆/日"))
steps = [
    ("全部成本 + 可執行性 + 舊 5x 門檻（文件舊設定）", dict(gate=True, exec_f=True)),
    ("  拿掉可執行性過濾", dict(gate=True, exec_f=False)),
    ("  再拿掉 13:25 平倉差", dict(gate=True, exec_f=False, fc=False)),
    ("  再拿掉停損觸價差", dict(gate=True, exec_f=False, fc=False, sl=False)),
    ("  再拿掉進場滑價 = 只剩手續費（舊表的口徑）", dict(gate=True, exec_f=False, fc=False, sl=False, slip=False)),
    ("  門檻改成開盤可成交額25%（現行 live）", dict(gate=False, exec_f=False, fc=False, sl=False, slip=False)),
    ("現行 live 完整（全部加回）", dict(gate=False, exec_f=True)),
]
prev = None
for label, kw in steps:
    r = run(**kw)
    d = "" if prev is None else "  (Δ %+8.1f%%)" % (r["total"] - prev)
    print("%-46s %9.1f %9.1f %10.2f %12s %7.1f%s" % (
        label, r["avg"], r["worst"], r["mdd"], "{:,.0f}".format(r["total"]), r["per_day"], d))
    prev = r["total"]
