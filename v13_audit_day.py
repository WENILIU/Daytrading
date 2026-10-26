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

from v13_engine import run_backtest, stats, exit_of, CAP0, COST

CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)


def build_table(date):
    cv, got, _ = run_backtest(capture=date, capital=CAP0, **CFG)
    A = got["A"]
    src = re.search(r'FINLAB_TOKEN = "([^"]+)"', open("gap_fade_auto.py", encoding="utf-8").read()).group(1)
    finlab.login(src)
    vol = pd.DataFrame(fdata.get("price:成交股數")); turn = pd.DataFrame(fdata.get("price:成交金額"))
    vol.index = pd.to_datetime(vol.index); turn.index = pd.to_datetime(turn.index)
    d = pd.Timestamp(date)
    rem = CAP0
    rows = []
    for _, r in A.sort_values("_rank").iterrows():
        pr = float(r["entry"]); pos = float(r["_weight"])
        code = str(r["stock"])
        ex, slp, reason, gross = exit_of(r["direction"], pr, float(r["day_high"]), float(r["day_low"]),
                                         float(r["day_close"]), float(r["lu"]), float(r["ld"]),
                                         float(r["tick"]), float(r["tp"]))
        net = gross - 2 * COST
        sh = float(int(pos * CAP0 / (pr * 1000)) * 1000)
        status = "可下"
        if sh < 1000:
            status = "跳過:整張不足(需 %.1f 萬, 1張=%.1f 萬)" % (pos * CAP0 / 1e4, pr * 1000 / 1e4)
            sh = 0.0
        elif sh * pr > rem:
            sh2 = float(int(rem / (pr * 1000)) * 1000)
            if sh2 < 1e-9:
                status = "跳過:資金已滿(剩 %.1f 萬)" % (rem / 1e4)
                sh = 0.0
            else:
                sh = sh2; status = "可下(縮量)"
        if sh > 0:
            rem -= sh * pr
        dv = float(vol.at[d, code]) if code in vol.columns and d in vol.index else np.nan
        dto = float(turn.at[d, code]) if code in turn.columns and d in turn.index else np.nan
        tpp = pr * (1 - float(r["tp"])) if r["direction"] == "SHORT" else pr * (1 + float(r["tp"]))
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
        })
    return cv, pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-10-21")
    ap.add_argument("--out", default=r"D:\AI專案\StockAgent\DayTrading")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(os.path.join(a.out, "per_stock"), exist_ok=True)
    cv, T = build_table(a.date)
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
    w("Gap Fade v13 - %s 逐筆審查（現行 V4 配置：k_model off / k_trail on / min_pos_pct 0.5%% / min_range 0.1%%）" % a.date)
    w("=" * 78)
    w("大盤開盤 Gap %+.2f%%，通過全部過濾的訊號 %d 個" % (row["market_ret"] * 100, int(row["n_signals"])))
    w("淨值距高峰回撤 %.2f%% -> 倉位倍數 %.1f；30 日邊際倍數 %s" %
      (row["cdd"] * 100, row["rs"], ("%.1f" % C["30日倍數"].iloc[0]) if len(C) else "n/a"))
    w("")
    w("A 策略設計面: %d 筆 / 曝險 %.1f%% / 當日 %+.3f%%" % (row["A_n"], row["A_expo"] * 100, row["A_pnl"] * 100))
    w("C 450 萬整張 : %d 筆 / 曝險 %.1f%% / 當日 %+.3f%% = %+.0f 元" %
      (row["C_n"], row["C_expo"] * 100, row["C_pnl"] * 100, C["盈虧(元)"].sum()))
    w("全期 A: CAGR %.1f%% MDD %.2f%% Sharpe %.2f" % (sa["cagr"], sa["mdd"], sa["sharpe"]))
    w("全期 C: CAGR %.1f%% MDD %.2f%% Sharpe %.2f" % (sc["cagr"], sc["mdd"], sc["sharpe"]))
    w("")
    w("C 實際會下的 %d 筆:" % len(C))
    for _, r in C.iterrows():
        w("  #%-3d %s %-5s 進場 %8.2f 出場 %8.2f %-18s 淨損益 %+6.2f%%  %2d 張 %7.1f 萬 %+9.0f 元" %
          (r["序"], r["股票"], r["方向"], r["進場價"], r["出場價"], r["出場原因"], r["淨損益%"],
           r["成交張數"], r["成交金額(萬)"], r["盈虧(元)"]))
    w("")
    w("設計想做但 450 萬買不到的 %d 筆（前 8）:" % (len(T) - len(C)))
    for _, r in T[~T["450萬狀態"].str.startswith("可下")].sort_values("序").head(8).iterrows():
        w("  #%-3d %s 模型分位 %.2f 設計權重 %.2f%% -> %s" %
          (r["序"], r["股票"], r["模型分位pred_q"], r["設計權重%"], r["450萬狀態"]))
    w("")
    w("這圖不能告訴你什麼：它是當日 OHLC 示意，不是盤中走勢（10/21 沒有 1 分 K，本地 1 分 K")
    w("只到 2025-03~2025-10 與 2026-01，富果 intraday/candles 目前金鑰回傳 0 筆）。")
    w("「先碰 TP 還是先碰 SL」「幾點碰到漲停」無法驗證；進出場價採與回測相同的 OHLC 規則")
    w("（先判 TP，再判 SL，否則 13:25 收盤價）。回測用 13:25，群益智慧單只能送 13:20。")
    open(os.path.join(a.out, "summary_%s.txt" % a.date.replace("-", "")), "w", encoding="utf-8-sig").write("\n".join(L))
    print("summary written")
