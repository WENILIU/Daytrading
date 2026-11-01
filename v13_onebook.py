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

  --fast   only the 450 萬-pinned book, all three liquidity rules, with the
           yearly book-level drawdown for each. Pinning the book removes capital
           size as a variable, so whatever the drawdown does over time is the
           market, not the account. That is the question the full table cannot
           answer, because every row there changes size and regime together.
"""
import warnings; warnings.filterwarnings("ignore")
import sys
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
FAST = "--fast" in sys.argv
if FAST:
    CAPS = [CAPS[0]]
YEARLY = "--yearly" in sys.argv


def run(cap, gate="dv", nozt=False):
    rule = dict(BASE)
    if gate == "dv":
        rule["dv_cap"] = K_OPEN * 0.25      # current live: cap the order
    elif gate == "dv10":
        rule["dv_cap"] = K_OPEN * 0.10      # same rule, half the participation
    else:
        rule["min_turnover_factor"] = 5.0   # the pre-2026-11-01 rule: gate the name
    book = float(CAP0); book_peak = float(CAP0); withdrawn = 0.0
    rows = []; books = []; n_all = 0; parts = []; expo = []; brake_days = 0
    trs = []
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
            # Counterfactual for the limit-capped stops: what holding to 13:25
            # would have paid instead. Without this the stop count is just a
            # number - it does not say whether the stop is earning its keep.
            dcl = float(r["day_close"])
            cf = (pr - dcl) / pr if r["direction"] == "SHORT" else (dcl - pr) / pr
            cf -= FC_COST
            # Still pinned at the limit when the session ends. This is the only
            # population where "do not stop at the limit" changes the operational
            # story - those are the orders the 13:25 settlement has to handle
            # instead of a normal fill. Everything else unlocked on its own.
            locked = (abs(dcl - float(r["lu"])) < 1e-6 if r["direction"] == "SHORT"
                      else abs(dcl - float(r["ld"])) < 1e-6)
            # nozt: do not let the price limit pull the stop in. For a SHORT the
            # limit-up price IS the worst case anyway, so stopping there buys
            # almost no protection while giving up the unlock. Measured below.
            if nozt and reason.startswith("停損(觸"):
                gross = cf
            if reason == "13:25 強制平倉":
                gross -= FC_COST
            if reason.startswith("停損"):
                gross -= SL_COST
            pred = notional / (K_OPEN * dv1) if (np.isfinite(dv1) and dv1 > 0) else np.nan
            gross -= 2 * COST + slip_cost(pred, 0.33)
            if np.isfinite(pred):
                parts.append(pred)
            rem -= notional; yuan += notional * gross; n_day += 1; n_all += 1
            trs.append((d, gross, reason, cf, notional, locked))
        expo.append((book - rem) / book)
        book += yuan
        if cap is not None and book > cap:
            withdrawn += book - cap; book = cap
        book_peak = max(book_peak, book)
        rows.append((d, book + withdrawn, yuan, n_day))
        books.append(book)
    idx = pd.to_datetime([x[0] for x in rows])
    wealth = pd.Series([x[1] for x in rows], index=idx)
    pnl = pd.Series([x[2] for x in rows], index=idx)
    yrs = (idx[-1] - idx[0]).days / 365.25
    cagr = (wealth.iloc[-1] / CAP0) ** (1 / yrs) - 1
    dd = (wealth - wealth.cummax()) / wealth.cummax()
    # The book is the risk unit. Its drawdown is the scale-invariant one, and
    # therefore the only one that says whether live will feel like the backtest.
    # Wealth MDD gets diluted by withdrawals: pin the book low and the
    # denominator grows while the risk unit does not, so the number shrinks
    # without the strategy getting any safer.
    bs = pd.Series(books, index=idx)
    ddb = (bs - bs.cummax()) / bs.cummax()
    ann = pnl.groupby(pnl.index.year).sum()
    P = np.array(parts) * 100 if parts else np.array([0.0])
    yearly = []
    for y in sorted(set(wealth.index.year)):
        seg = wealth[wealth.index.year == y]
        ydd = ((seg - seg.cummax()) / seg.cummax()).min() * 100
        bseg = bs[bs.index.year == y]
        yddb = ((bseg - bseg.cummax()) / bseg.cummax()).min() * 100
        yearly.append((y, ydd, yddb, len(seg)))
    return dict(yearly=yearly,
                wealth=wealth.iloc[-1], withdrawn=withdrawn, cagr=cagr * 100,
                mdd=dd.min() * 100, worst_year=ann.min() / 1e4, ann=ann,
                mdd_book=ddb.min() * 100,
                per_day=n_all / len(rows), brake=brake_days / len(rows) * 100,
                p50=np.percentile(P, 50), p90=np.percentile(P, 90),
                expo=np.percentile(np.array(expo), 50), final_book=book,
                trades=trs, rows=rows)


if YEARLY:
    # The shipped configuration: book pinned at 4.5M, order size capped at 10 pct
    # of the opening auction. This is the one row where the account simulated IS
    # the account live has, so a year below is what a real year would look like -
    # including that the drawdown has been getting worse while the profit per
    # year has not.
    r = run(4_500_000, "dv10")
    T = pd.DataFrame(r["trades"], columns=["date", "net", "reason", "cf", "notional", "locked"])
    T["y"] = pd.to_datetime(T["date"]).dt.year

    def why(s):
        if s.startswith("停損(觸"):
            return "SLz"
        if s.startswith("停損"):
            return "SL"
        if s.startswith("停利"):
            return "TP"
        return "FC"

    T["k"] = T["reason"].map(why)
    G = T.groupby("y")
    print()
    print("=" * 112)
    print("逐年完整績效：部位釘在 450 萬、單筆上限=開盤可成交額 10%、整張、零融資、成本全含、可執行性已過濾")
    print("=" * 112)
    # The stop split is the point of this mode. A stop count on its own does not
    # say whether the stop is earning its keep, so every stop row also carries the
    # counterfactual: what holding to 13:25 would have paid instead.
    print("%-6s %5s %6s %7s %9s %10s %9s | %7s %7s %10s %10s %11s %11s" % (
        "年", "交易日", "筆數", "勝率%", "平均每筆%", "年利得(萬)", "部位MDD%",
        "正常SL%", "觸漲停%", "正常SL均虧", "觸漲停均虧", "觸漲停持有%", "停損拖累(萬)"))
    yb = {y: (ydd, yddb, nseg) for y, ydd, yddb, nseg in r["yearly"]}
    tot = 0.0
    for y, g in G:
        n = len(g); win = (g["net"] > 0).mean() * 100
        yuan = r["ann"].get(y, 0.0); tot += yuan
        c = g["k"].value_counts()
        sl = g[g["k"] == "SL"]; slz = g[g["k"] == "SLz"]
        drag = (sl["net"] * sl["notional"]).sum() / 1e4
        print("%-6d %5d %6d %7.1f %9.3f %10.0f %9.2f | %7.1f %7.1f %10.2f %10.2f %11.2f %11.0f" % (
            y, yb[y][2], n, win, g["net"].mean() * 100, yuan / 1e4, yb[y][1],
            len(sl) / n * 100, len(slz) / n * 100,
            sl["net"].mean() * 100 if len(sl) else 0.0,
            slz["net"].mean() * 100 if len(slz) else 0.0,
            slz["cf"].mean() * 100 if len(slz) else 0.0, drag))
    print("-" * 112)
    allsl = T[T["k"] == "SL"]; allz = T[T["k"] == "SLz"]
    print("%-6s %5s %6d %7.1f %9.3f %10.0f %9s | %7.1f %7.1f %10.2f %10.2f %11.2f %11.0f" % (
        "合計", "", len(T), (T["net"] > 0).mean() * 100, T["net"].mean() * 100, tot / 1e4, "",
        len(allsl) / len(T) * 100, len(allz) / len(T) * 100, allsl["net"].mean() * 100,
        allz["net"].mean() * 100, allz["cf"].mean() * 100,
        (allsl["net"] * allsl["notional"]).sum() / 1e4))
    print()
    print("觸漲停停損：停損價被漲跌停壓到比 4%% 更近的位置，所以虧損比 4%% 小。")
    print("  「觸漲停持有%」= 這些單如果不停損、改由 13:25 強制平倉的平均損益。正數代表停損是對的。")
    z = T[T["k"] == "SLz"]
    if len(z):
        print("  合計 %d 筆。停損比持有到 13:25 好：%d 筆（%.1f%%）。" % (
            len(z), int((z["net"] > z["cf"]).sum()), (z["net"] > z["cf"]).mean() * 100))
        zl = z[z["locked"]]
        print("  其中到 13:25 仍然鎖在漲跌停：%d 筆（%.1f%%），平均虧 %.2f%%。" % (
            len(zl), len(zl) / len(z) * 100, zl["cf"].mean() * 100 if len(zl) else 0.0))
        print("  這 %d 筆才是需要 13:25 結算機制處理的；其餘 %d 筆自己解開了。" % (
            len(zl), len(z) - len(zl)))
    print()
    print("最終財富 %s（其中已出金 %s）、財富 CAGR %.1f%%、部位 MDD %.2f%%、財富 MDD %.2f%%" % (
        "{:,.0f}".format(r["wealth"]), "{:,.0f}".format(r["withdrawn"]), r["cagr"],
        r["mdd_book"], r["mdd"]))
    print("部位釘在 450 萬，所以年利得全部等同出金；部位報酬% = 年利得 / 450 萬。")

    print()
    print("=" * 100)
    print("對照組：把「漲停壓縮停損」拿掉 → 停損一律 4%，觸漲停不停損，改由 13:25 平倉")
    print("=" * 100)
    r2 = run(4_500_000, "dv10", nozt=True)
    T2 = pd.DataFrame(r2["trades"], columns=["date", "net", "reason", "cf", "notional", "locked"])
    T2["y"] = pd.to_datetime(T2["date"]).dt.year
    yb2 = {y: (ydd, yddb, nseg) for y, ydd, yddb, nseg in r2["yearly"]}
    print("%-6s %12s %12s %9s | %10s %10s %9s" % (
        "年", "現行利得(萬)", "改後利得(萬)", "差(萬)", "現行MDD%", "改後MDD%", "改後勝率%"))
    for y in sorted(r2["ann"].index):
        a = r["ann"].get(y, 0.0); b = r2["ann"].get(y, 0.0)
        print("%-6d %12.0f %12.0f %9.0f | %10.2f %10.2f %9.1f" % (
            y, a / 1e4, b / 1e4, (b - a) / 1e4, yb[y][1], yb2[y][1],
            (T2[T2["y"] == y]["net"] > 0).mean() * 100))
    print("-" * 100)
    s2 = float(r2["ann"].sum())
    print("%-6s %12.0f %12.0f %9.0f | %10.2f %10.2f %9.1f" % (
        "全期", tot / 1e4, s2 / 1e4, (s2 - tot) / 1e4, r["mdd_book"], r2["mdd_book"],
        (T2["net"] > 0).mean() * 100))
    print()
    print("現行：財富 CAGR %.1f%%、部位 MDD %.2f%%、最終財富 %s" % (
        r["cagr"], r["mdd_book"], "{:,.0f}".format(r["wealth"])))
    print("改後：財富 CAGR %.1f%%、部位 MDD %.2f%%、最終財富 %s" % (
        r2["cagr"], r2["mdd_book"], "{:,.0f}".format(r2["wealth"])))
    raise SystemExit(0)


print()
print("450 萬起、整張、零融資、單量<=開盤可成交額25%、成本全含、可執行性已過濾")
print("回撤煞車一律接在「交易帳戶自己的淨值曲線」，也就是 live 讀 equity_state.json 看到的東西")
print("部位MDD = 交易帳戶自己的回撤，與資金大小無關，这才是實盤會感覺到的那個")
print("%-24s %9s %8s %8s %9s %11s %11s | %6s %6s %6s %6s" % (
    "交易部位上限", "財富CAGR", "部位MDD", "財富MDD", "最差年(萬)", "最終財富", "已出金",
    "筆/日", "煞車日%", "曝險%", "參與p90"))
GATES = [("單筆上限=開盤可成交額25%（現行 live）", "dv"),
         ("單筆上限=開盤可成交額10%（保守參與率）", "dv10"),
         ("T-1 成交額 < 5x淨值 才交易（舊的 factor=5）", "f5")]
res = {}
allres = {}
for gl, gg in GATES:
    print()
    print("=" * 118)
    print("流動性規則：%s" % gl)
    print("=" * 118)
    print("%-24s %9s %8s %8s %9s %11s %11s | %6s %6s %6s %6s" % (
        "交易部位上限", "財富CAGR", "部位MDD", "財富MDD", "最差年(萬)", "最終財富", "已出金",
        "筆/日", "煞車日%", "曝險%", "參與p90"))
    res = {}
    for label, cap in CAPS:
        r = run(cap, gg)
        res[label] = r
        allres[(gl, label)] = r
        print("%-24s %8.1f%% %7.2f%% %7.2f%% %9.0f %11s %11s | %6.1f %6.1f %6.1f %6.1f" % (
            label, r["cagr"], r["mdd_book"], r["mdd"], r["worst_year"],
            "{:,.0f}".format(r["wealth"]),
            "{:,.0f}".format(r["withdrawn"]), r["per_day"], r["brake"], r["expo"] * 100, r["p90"]))
print()
print("全部 %d 個組合，按「部位 MDD 不劣於 -5%%」過濾後比 CAGR：" % len(allres))
ok = [(k[0], k[1], v["cagr"], v["mdd_book"], v["mdd"]) for k, v in allres.items()
      if v["mdd_book"] >= -5.0]
for gl, label, c, mb, mw in sorted(ok, key=lambda x: -x[2]):
    print("  CAGR %6.1f%%  部位MDD %6.2f%%（財富MDD %6.2f%%）  <-  %s | 部位上限 %s" % (
        c, mb, mw, gl, label))
bk = max(((k, v) for k, v in allres.items() if v["mdd_book"] >= -5.0),
         key=lambda kv: kv[1]["cagr"])
print()
print("部位 MDD 不劣於 -5%% 的最高 CAGR：%s | 部位上限 %s -> CAGR %.1f%% / 部位MDD %.2f%%" % (
    bk[0][0], bk[0][1], bk[1]["cagr"], bk[1]["mdd_book"]))
b = bk[1]
res = {k[1]: v for k, v in allres.items() if k[0] == bk[0][0]}
print("  逐年總利得（萬元）：")
print("   ", {int(k): round(v / 1e4, 0) for k, v in b["ann"].items()})
print("  最終交易部位 %s、已出金 %s、最終財富 %s" % (
    "{:,.0f}".format(b["final_book"]), "{:,.0f}".format(b["withdrawn"]), "{:,.0f}".format(b["wealth"])))

print()
if FAST:
    print()
    print("=" * 100)
    print("部位釘在 450 萬：資金規模已固定，逐年回撤只剩市場環境這個變因")
    print("=" * 100)
    for gl, gg in GATES:
        r = run(CAPS[0][1], gg)
        print()
        print("  %s" % gl)
        print("    %-6s %9s %9s %9s %9s" % ("年", "部位MDD%", "財富MDD%", "年利得(萬)", "交易日"))
        for y, ydd, yddb, nseg in r["yearly"]:
            g = r["ann"].get(y, 0.0)
            print("    %-6d %9.2f %9.2f %9.0f %9d" % (y, yddb, ydd, g / 1e4, nseg))
        print("    -> 全期 部位MDD %.2f%%、財富CAGR %.1f%%、筆/日 %.1f" % (
            r["mdd_book"], r["cagr"], r["per_day"]))
    raise SystemExit(0)

print("逐年實際經歷（左=交易帳戶回撤，右=含出金的財富回撤）")
print("全期 MDD 是被後段部位變大那年拉高的，下面才是 450 萬這個規模會感覺到的東西")
for label in ("450 萬（每筆獲利都取出）", bk[0][1], "不設上限"):
    r = res[label]
    print()
    print("  %s" % label)
    print("    %-6s %9s %9s %9s %9s" % ("年", "部位MDD%", "財富MDD%", "年利得(萬)", "交易日"))
    for y, ydd, yddb, nseg in r["yearly"]:
        g = r["ann"].get(y, 0.0)
        print("    %-6d %9.2f %9.2f %9.0f %9d" % (y, yddb, ydd, g / 1e4, nseg))
    first = r["yearly"][0]
    print("    -> 第一年 部位MDD %.2f%%（這是 450 萬起步時實際會遇到的量級）" % first[2])
