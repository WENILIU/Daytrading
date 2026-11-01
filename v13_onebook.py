"""The one book. What gap_fade_auto.py will actually do, simulated the same way.

Every performance number in this repo has been a function of one undecided thing:
what happens to the profits. It is not a cosmetic choice, because dd_scale keys
off the book's own equity curve - pin the book and the brake can never fire,
let it compound and the brake fires on every later drawdown. That single
decision is worth more than any parameter in the strategy.

So simulate the account, not a return series:

  book starts at 4_500_000.
  each day: dd_scale from the book's own peak (exactly what live reads from
            equity_state.json), size off the book, whole lots, zero margin.
  after the day: book += pnl. if book > cap, the excess is withdrawn.
  total wealth = book + cumulative withdrawals. That is the curve the owner has.

cap = 4_500_000 is "take every profit out"; cap = None is "never take any out".
Everything between is a real instruction you can give yourself. For each one the
backtest and live agree by construction, because both are this loop.

Exits are v13_engine.exit_of_legal - the same rule the exchange executes for the
smart order (stop capped at the price limit, 13:25 close). Not the model's
training target, which differs by 0.206 pct a trade; that difference is a
model-target mismatch, not a measurement choice, and it does not change which
number is right here.

Usage: python v13_onebook.py
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
days = sorted(D["date"].unique())
FCD = FCD.reindex(index=days, columns=sorted(D["stock"].unique()))
DTV = DTV.reindex(index=days, columns=sorted(D["stock"].unique()))
fcd = FCD.fillna(False).astype(bool).values; dtv = DTV.values
dp = {d: i for i, d in enumerate(FCD.index.values)}
fp = {c: j for j, c in enumerate(FCD.columns)}; gp = {c: j for j, c in enumerate(DTV.columns)}
ri = np.array([dp[d] for d in D["date"].values])
cj = D["stock"].map(fp).fillna(-1).astype(int).values
gj = D["stock"].map(gp).fillna(-1).astype(int).values
D["blocked"] = ((cj >= 0) & fcd[ri, np.clip(cj, 0, fcd.shape[1] - 1)]) | \
               ((gj >= 0) & (dtv[ri, np.clip(gj, 0, dtv.shape[1] - 1)] == 0))
print("signals %d, blocked by executability %d" % (len(D), int(D["blocked"].sum())), flush=True)

GROUPS = {d: g[~g["blocked"]] for d, g in D.groupby("date")}
CAPS = [("450 萬（每筆獲利都取出）", 4_500_000), ("1,000 萬", 10_000_000),
        ("2,000 萬", 20_000_000), ("5,000 萬", 50_000_000),
        ("1 億", 100_000_000), ("不設上限", None)]


def run(cap):
    rule = dict(BASE); rule["dv_cap"] = K_OPEN * 0.25
    book = float(CAP0); book_peak = float(CAP0); withdrawn = 0.0
    rows = []; n_all = 0; parts = []; expo = []; brake_days = 0
    for d in days:
        cdd = (book - book_peak) / book_peak
        rs = 0.30 if cdd < -0.006 else (0.12 if cdd < -0.012 else 1.0)
        if rs < 1.0:
            brake_days += 1
        rem = book; n_day = 0; yuan = 0.0
        for _, r in GROUPS[d].sort_values("_rank").iterrows():
            if n_day >= 30:
                break
            pr = float(r["entry"]); code = str(r["stock"])
            w = float(r["_weight"]) / (float(r["_rs"]) or 1.0) * rs
            dv1 = float(TO1.at[d, code]) if (code in TO1.columns and d in TO1.index) else np.nan
            n = S.lots_for(rule, w, pr, rem, dv1, capital=book)
            if n <= 0:
                continue
            notional = n * 1000.0 * pr
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
        expo.append((book - rem) / book)
        book += yuan
        if cap is not None and book > cap:
            withdrawn += book - cap; book = cap
        book_peak = max(book_peak, book)
        rows.append((d, book + withdrawn, yuan, n_day))
    idx = pd.to_datetime([x[0] for x in rows])
    wealth = pd.Series([x[1] for x in rows], index=idx)
    pnl = pd.Series([x[2] for x in rows], index=idx)
    yrs = (idx[-1] - idx[0]).days / 365.25
    cagr = (wealth.iloc[-1] / CAP0) ** (1 / yrs) - 1
    dd = (wealth - wealth.cummax()) / wealth.cummax()
    ann = pnl.groupby(pnl.index.year).sum()
    P = np.array(parts) * 100 if parts else np.array([0.0])
    yearly = []
    for y in sorted(set(wealth.index.year)):
        seg = wealth[wealth.index.year == y]
        ydd = ((seg - seg.cummax()) / seg.cummax()).min() * 100
        yearly.append((y, ydd, len(seg)))
    return dict(yearly=yearly,
                wealth=wealth.iloc[-1], withdrawn=withdrawn, cagr=cagr * 100,
                mdd=dd.min() * 100, worst_year=ann.min() / 1e4, ann=ann,
                per_day=n_all / len(rows), brake=brake_days / len(rows) * 100,
                p50=np.percentile(P, 50), p90=np.percentile(P, 90),
                expo=np.percentile(np.array(expo), 50), final_book=book)


print()
print("450 萬起、整張、零融資、單量<=開盤可成交額25%、成本全含、可執行性已過濾")
print("回撤煞車一律接在「交易帳戶自己的淨值曲線」，也就是 live 讀 equity_state.json 看到的東西")
print("%-24s %9s %8s %9s %11s %11s | %6s %6s %6s %6s" % (
    "交易部位上限", "財富CAGR", "財富MDD", "最差年(萬)", "最終財富", "已出金", "筆/日", "煞車日%", "曝險%", "參與p90"))
res = {}
for label, cap in CAPS:
    r = run(cap)
    res[label] = r
    print("%-24s %8.1f%% %7.2f%% %9.0f %11s %11s | %6.1f %6.1f %6.1f %6.1f" % (
        label, r["cagr"], r["mdd"], r["worst_year"], "{:,.0f}".format(r["wealth"]),
        "{:,.0f}".format(r["withdrawn"]), r["per_day"], r["brake"], r["expo"] * 100, r["p90"]))
best = max(res.items(), key=lambda kv: kv[1]["cagr"] if kv[1]["mdd"] >= -5.0 else -1e9)
print()
print("MDD 不劣於 -5%% 的最高 CAGR：%s -> CAGR %.1f%% / MDD %.2f%%" % (
    best[0], best[1]["cagr"], best[1]["mdd"]))
b = best[1]
print("  逐年總利得（萬元）：")
print("   ", {int(k): round(v / 1e4, 0) for k, v in b["ann"].items()})
print("  最終交易部位 %s、已出金 %s、最終財富 %s" % (
    "{:,.0f}".format(b["final_book"]), "{:,.0f}".format(b["withdrawn"]), "{:,.0f}".format(b["wealth"])))

print()
print("逐年實際經歷（財富曲線在該年內從高點跌下去最多多少）")
print("全期 MDD 是被後段部位變大那年拉高的，下面才是 450 萬這個規模會感覺到的東西")
for label in ("450 萬（每筆獲利都取出）", "1 億", "不設上限"):
    r = res[label]
    print()
    print("  %s" % label)
    print("    %-6s %9s %9s %9s" % ("年", "MDD%", "年利得(萬)", "交易日"))
    for y, ydd, nseg in r["yearly"]:
        g = r["ann"].get(y, 0.0)
        print("    %-6d %9.2f %9.0f %9d" % (y, ydd, g / 1e4, nseg))
    first = r["yearly"][0]
    print("    -> 第一年 MDD %.2f%%（這是 450 萬起步時實際會遇到的量級）" % first[1])
