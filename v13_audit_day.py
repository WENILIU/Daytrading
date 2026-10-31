"""One-day visual audit for Gap Fade v13.

Uses the single evaluation engine (v13_engine) so the charts can never drift from
the published numbers. Produces, for one trading day:
  audit_grid_<date>_450萬實際交易.png   the orders a 4,500,000 account can place
  audit_grid_<date>_top12.png          top-12 by model score, marked buyable or not
  per_stock/<date>_<rank>_<code>.png   full-size single-stock panel
  summary_<date>.txt                   day-level numbers + what the charts cannot show
  equity_up_to_<date>.png              equity curve, design view vs 450wan whole lots

Usage: python v13_audit_charts.py --date 2026-10-21
"""
import argparse, os, re, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
for _f in ["C:/Windows/Fonts/msjh.ttc"]:
    if os.path.exists(_f):
        fm.fontManager.addfont(_f)
plt.rcParams["font.family"] = "Microsoft JhengHei"
plt.rcParams["axes.unicode_minus"] = False
import finlab
from finlab import data as fdata

from v13_engine import run_backtest, stats, exit_of, exit_of_legal, CAP0, COST, SLO
import v13_sizing as S

CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)


def build_table(date):
    cv, got, _ = run_backtest(capture=date, capital=CAP0, **CFG)
    # D = raw design intent (before any cash / whole-lot filter). A is itself
    # filtered by its own cash loop, so it understates what the model asked for.
    A = got["D"]
    src = re.search(r'FINLAB_TOKEN = "([^"]+)"', open("gap_fade_auto.py", encoding="utf-8").read()).group(1)
    finlab.login(src)
    vol = pd.DataFrame(fdata.get("price:成交股數")); turn = pd.DataFrame(fdata.get("price:成交金額"))
    TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
    # Whether a name may be day traded at all. Two per-date sources, both T-1 safe:
    # the exchange full-cash-delivery list, and names the exchange recorded zero
    # day-trade volume for over 20 sessions. Neither is in signals_v13 - the signal
    # pool only excludes 處置 and un-borrowable SHORTs - and both make a printed
    # order impossible to execute, so the audit says it on the row.
    import pickle
    FCD = pd.read_pickle(r"D:\gapfade_data\fcd_panel_full.pkl")
    FCD.columns = [str(c) for c in FCD.columns]
    _dl = pickle.load(open(r"D:\gapfade_data\daytrade_dead_list.pkl", "rb"))
    DEAD = {pd.Timestamp(k): {str(c) for c in v} for k, v in _dl["days"].items()}
    DEAD_KEYS = sorted(DEAD)

    def daytrade_block(d, code):
        why = []
        try:
            if code in FCD.columns and bool(FCD.at[d, code]):
                why.append("全額交割")
        except KeyError:
            pass
        ks = [k for k in DEAD_KEYS if k <= d]
        if ks and code in DEAD[ks[-1]]:
            why.append("近20日零當沖量")
        return "、".join(why)
    vol.index = pd.to_datetime(vol.index); turn.index = pd.to_datetime(turn.index)
    d = pd.Timestamp(date)
    rem = CAP0
    rows = []
    for _, r in A.sort_values("_rank").iterrows():
        pr = float(r["entry"]); pos = float(r["_weight"])
        code = str(r["stock"])
        # T-1 turnover must exist before the order size is decided
        dv1 = float(TO1.at[d, code]) if code in TO1.columns and d in TO1.index else np.nan
        lu = float(r["lu"]); ld = float(r["ld"]); tk = float(r["tick"]); tpv = float(r["tp"])
        ex, slp, tpp, reason, gross = exit_of_legal(r["direction"], pr, float(r["day_high"]),
                                                    float(r["day_low"]), float(r["day_close"]),
                                                    lu, ld, tk, tpv)
        if r["direction"] == "SHORT":
            sl_raw = min(pr * (1 + SLO), lu - tk); tp_raw = pr * (1 - tpv)
        else:
            sl_raw = max(pr * (1 - SLO), ld + tk); tp_raw = pr * (1 + tpv)
        net = gross - 2 * COST
        # same order rule as the live trader and the published trade list
        n_full = S.lots_for(S.R9, pos, pr, CAP0, dv1, capital=CAP0)
        n = S.lots_for(S.R9, pos, pr, rem, dv1, capital=CAP0)
        sh = n * 1000.0
        status = "可下"
        if n <= 0:
            sh = 0.0
            reason = S.skip_reason(S.R9, pos, pr, dv1, capital=CAP0)
            status = "跳過:" + (reason or "資金已滿")
        elif n < n_full:
            status = "可下(縮量)"
        if sh > 0:
            rem -= sh * pr
        dv = float(vol.at[d, code]) if code in vol.columns and d in vol.index else np.nan
        dto = float(turn.at[d, code]) if code in turn.columns and d in turn.index else np.nan
        rows.append({
            "日期": date, "序": int(r["_rank"]), "股票": code, "方向": r["direction"],
            "成交張數": int(sh / 1000), "成交股數": int(sh), "成交金額(萬)": round(sh * pr / 1e4, 2),
            "進場價": round(pr, 2), "前收": round(float(r["prev_close"]), 2),
            "原始gap%": round(float(r["raw_gap"]) * 100, 2), "調整後gap%": round(float(r["adj_gap"]) * 100, 2),
            "大盤開盤gap%": round(float(r["market_ret"]) * 100, 2),
            "漲停價": round(float(r["lu"]), 2), "跌停價": round(float(r["ld"]), 2),
            "進場距漲停%": round(float(r["zt_dist"]) * 100, 2),
            "日高": round(float(r["day_high"]), 2), "日低": round(float(r["day_low"]), 2),
            "收盤": round(float(r["day_close"]), 2),
            "停損價": round(slp, 2), "停利價": round(tpp, 2), "停利TP%": round(float(r["tp"]) * 100, 1),
            "停損價(未取整)": round(sl_raw, 3), "停利價(未取整)": round(tp_raw, 3),
            "價位需取整": bool(abs(slp - sl_raw) > 1e-9 or abs(tpp - tp_raw) > 1e-9),
            "出場價": round(ex, 2), "出場原因": reason,
            "毛損益%": round(gross * 100, 2), "淨損益%": round(net * 100, 2),
            "盈虧(元)": round(sh * pr * net),
            "模型分位pred_q": round(float(r["pred_q"]), 3), "TP分位q1": round(float(r["q1"]), 3),
            "基礎倉位%": round(float(r["base_pos"]) * 100, 1), "設計權重%": round(pos * 100, 3),
            "ZT倍數": float(r["_zm"]), "30日倍數": round(float(r["_kT"]), 3), "淨值回撤倍數": float(r["_rs"]),
            "450萬狀態": status,
            "當日成交股數": dv, "當日成交額(萬)": round(dto / 1e4, 1) if np.isfinite(dto) else np.nan,
            "我占當日額%": round(sh * pr / dto * 100, 3) if np.isfinite(dto) and dto > 0 and sh > 0 else np.nan,
            "整天只成交一個價格": bool(abs(float(r["day_high"]) - float(r["day_low"])) < 1e-9),
            "當沖可執行": daytrade_block(d, code) or "OK",
        })
    meta = {"dead_list_asof": str(_dl["asof"])[:10], "fcd_last": str(FCD.index.max())[:10]}
    return cv, pd.DataFrame(rows), meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-10-21")
    ap.add_argument("--out", default=r"D:\AI專案\StockAgent\DayTrading")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(os.path.join(a.out, "per_stock"), exist_ok=True)
    cv, T, META = build_table(a.date)
    T.to_pickle("_audit_T.pkl"); cv.to_pickle("_audit_curve.pkl")
    T.to_csv(os.path.join(a.out, "trades_%s_all.csv" % a.date.replace("-", "")), index=False, encoding="utf-8-sig")
    C = T[T["450萬狀態"].str.startswith("可下")]
    C.to_csv(os.path.join(a.out, "trades_%s_450萬實際成交.csv" % a.date.replace("-", "")), index=False, encoding="utf-8-sig")
    row = cv.loc[pd.Timestamp(a.date)]
    print("signals sized:", len(T), "buyable at 4.5M:", len(C))
    print("design day %.3f%%  450wan day %.3f%%" % (row["A_pnl"] * 100, row["C_pnl"] * 100))
    print(C[["序", "股票", "方向", "進場價", "出場價", "出場原因", "淨損益%", "成交張數", "成交金額(萬)", "盈虧(元)"]].to_string(index=False))
    import v13_audit_charts_draw as D
    D.draw(a.date, T, C, cv, a.out)
    sa = stats(cv["A_pnl"]); sc = stats(cv["C_pnl"])
    L = []
    w = L.append
    w("Gap Fade v13 - %s 逐筆審查（現行 V6 配置：k_model off / k_trail on / min_pos_pct 0.5%% / "
      "min_range 0.1%% / 漲停價、停損價、停利價皆為交易所合法價格，"
      "且漲停-1價比較已消除浮點誤差）" % a.date)
    w("=" * 78)
    w("大盤開盤 Gap %+.2f%%，通過全部過濾的訊號 %d 個" % (row["market_ret"] * 100, int(row["n_signals"])))
    # kT is keyed by (date, direction) in v13_engine, so it is a per-direction
    # regime multiplier, not a per-stock one. Printing one row's value made it read
    # like a stock-level judgement. Show both directions explicitly.
    kt = T.groupby("方向")["30日倍數"].agg(["min", "max"])
    kts = "、".join("%s %.3f" % (d, float(kt.at[d, "min"])) for d in ["LONG", "SHORT"] if d in kt.index)
    w("淨值距高峰回撤 %.2f%% -> 倉位倍數 %.1f" % (row["cdd"] * 100, row["rs"]))
    w("30 日邊際倍數（按方向，非按個股）：%s" % (kts or "n/a"))
    w("")
    w("A 策略設計面: %d 筆 / 曝險 %.1f%% / 當日 %+.3f%%" % (row["A_n"], row["A_expo"] * 100, row["A_pnl"] * 100))
    own_yuan = float(C["盈虧(元)"].sum())
    own_expo = float(C["成交金額(萬)"].sum()) * 1e4 / CAP0 * 100
    w("C 450 萬整張（R9 現行下單規則：含參與率上限、1 張過大過濾、整張限制）: "
      "%d 筆 / 曝險 %.1f%% / 當日 %+.3f%% = %+.0f 元" %
      (len(C), own_expo, own_yuan / CAP0 * 100, own_yuan))
    w("  同一日回測引擎的 C（v13_engine.allocate，沒有參與率上限也沒有 1 張過大過濾）: "
      "%d 筆 / %+.3f%%。兩者不是同一本書，差的就是那兩條過濾。" %
      (row["C_n"], row["C_pnl"] * 100))
    w("全期 A（設計面，無資金與整張限制）: CAGR %.1f%% MDD %.2f%% Sharpe %.2f" %
      (sa["cagr"], sa["mdd"], sa["sharpe"]))
    w("全期 C（回測引擎 allocate 規則，非上方 R9）: CAGR %.1f%% MDD %.2f%% Sharpe %.2f" %
      (sc["cagr"], sc["mdd"], sc["sharpe"]))
    w("")
    w("C 實際會下的 %d 筆:" % len(C))
    for _, r in C.iterrows():
        w("  #%-3d %s %-5s 進場 %8.2f 出場 %8.2f %-18s 淨損益 %+6.2f%%  %2d 張 %7.1f 萬 %+9.0f 元" %
          (r["序"], r["股票"], r["方向"], r["進場價"], r["出場價"], r["出場原因"], r["淨損益%"],
           r["成交張數"], r["成交金額(萬)"], r["盈虧(元)"]))
    w("")
    nb = C[C["當沖可執行"] != "OK"]
    w("會下、但交易所說這檔不能當沖的 %d 筆:" % len(nb))
    for _, r in nb.sort_values("序").iterrows():
        w("  #%-3d %s %-5s -> %s" % (r["序"], r["股票"], r["方向"], r["當沖可執行"]))
    if not len(nb):
        w("  （無）")
    w("  來源：全額交割逐日清單（停在 %s）、交易所逐股當沖成交量（as-of %s），兩者由 refresh_executability_panels.py 每日刷新。這是「這檔能不能當沖」，不是這個帳戶的 924 無券當沖資格，兩者要分開看。" % (META["fcd_last"], META["dead_list_asof"]))
    w("")
    w("設計想做但 450 萬買不到的 %d 筆（前 8）:" % (len(T) - len(C)))
    for _, r in T[~T["450萬狀態"].str.startswith("可下")].sort_values("序").head(8).iterrows():
        w("  #%-3d %s 模型分位 %.2f 設計權重 %.2f%% -> %s" %
          (r["序"], r["股票"], r["模型分位pred_q"], r["設計權重%"], r["450萬狀態"]))
    w("")
    nfix = int(T["價位需取整"].sum())
    dmax = 0.0
    for _, r in T.iterrows():
        if r["價位需取整"] and r["成交股數"] > 0:
            dmax = max(dmax, abs(r["停損價"] - r["停損價(未取整)"]) * r["成交股數"],
                       abs(r["停利價"] - r["停利價(未取整)"]) * r["成交股數"])
    w("停損/停利價已對齊交易所合法價位（間隔 <10:0.01 / 10-50:0.05 / 50-100:0.1 /")
    w("100-500:0.5 / 500-1000:1.0 / >=1000:5.0）。CSV「停損價(未取整)」是回測用的連續價，")
    w("未對齊的訂單會被交易所退單。本日 %d/%d 筆需要取整，本日最大單筆損益差 %.0f 元。" % (nfix, len(T), dmax))
    w("")
    w("這圖不能告訴你什麼：它是當日 OHLC 示意，不是盤中走勢（%s 沒有 1 分 K，本地 1 分 K" % a.date)
    w("只到 2025-03~2025-10 與 2026-01，富果 intraday/candles 目前金鑰回傳 0 筆）。")
    w("「先碰 TP 還是先碰 SL」「幾點碰到漲停」無法驗證；進出場價採與回測相同的 OHLC 規則")
    w("（先判 TP，再判 SL，否則 13:25 收盤價）。回測用 13:25，群益智慧單只能送 13:20。")
    open(os.path.join(a.out, "summary_%s.txt" % a.date.replace("-", "")), "w", encoding="utf-8-sig").write("\n".join(L))
    print("summary written")
