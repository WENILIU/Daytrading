"""Generate the per-trade live plan for a date window at a fixed account size.

Writes daytrading.csv: every order the strategy would actually place (whole lots,
no margin) with the same fields the audit charts show, plus a running cash balance.
"""
import argparse, os, re, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from v13_engine import run_backtest, stats, exit_of, exit_of_legal, CAP0, COST, SLO

OUT = r"D:\AI專案\StockAgent\DayTrading\daytrading.csv"

ap = argparse.ArgumentParser()
ap.add_argument("--since", default="2026-07-23")
ap.add_argument("--until", default="2026-10-22")
ap.add_argument("--capital", type=float, default=CAP0)
ap.add_argument("--min-weight", type=float, default=0.005)
ap.add_argument("--min-range", type=float, default=0.001)
ap.add_argument("--out", default=OUT)
a = ap.parse_args()

cv, got, _ = run_backtest(capture=(a.since, a.until), capital=a.capital,
                          min_weight=a.min_weight, kmode="one", tmode="on",
                          min_range=a.min_range)
C = got["C"]
print("captured rows:", len(C), "days:", cv.loc[a.since:a.until].shape[0])

import finlab
from finlab import data as fdata
tok = re.search(r'FINLAB_TOKEN = "([^"]+)"', open("gap_fade_auto.py", encoding="utf-8").read()).group(1)
finlab.login(tok)
vol = fdata.get("price:成交股數")
turn = fdata.get("price:成交金額")
vol = pd.DataFrame(vol); turn = pd.DataFrame(turn)
vol.index = pd.to_datetime(vol.index); turn.index = pd.to_datetime(turn.index)

rows = []
for _, r in C.iterrows():
    d = pd.Timestamp(r["date"])
    code = str(r["stock"])
    pr = float(r["entry"]); lu = float(r["lu"]); ld = float(r["ld"]); tk = float(r["tick"]); tpv = float(r["tp"])
    ex, slp, tpp, reason, gross = exit_of_legal(r["direction"], pr, float(r["day_high"]),
                                                float(r["day_low"]), float(r["day_close"]),
                                                lu, ld, tk, tpv)
    if r["direction"] == "SHORT":
        sl_raw = min(pr * (1 + SLO), lu - tk); tp_raw = pr * (1 - tpv)
    else:
        sl_raw = max(pr * (1 - SLO), ld + tk); tp_raw = pr * (1 + tpv)
    ex_raw, _, _, gross_raw = exit_of(r["direction"], pr, float(r["day_high"]), float(r["day_low"]),
                                      float(r["day_close"]), lu, ld, tk, tpv)
    net = gross - 2 * COST
    notional = float(r["_notional"])
    dv = float(vol.at[d, code]) if code in vol.columns and d in vol.index else np.nan
    dto = float(turn.at[d, code]) if code in turn.columns and d in turn.index else np.nan
    rows.append({
        "日期": d.strftime("%Y-%m-%d"), "序": int(r["_rank"]), "股票": code, "方向": r["direction"],
        "成交張數": int(r["_shares"] / 1000), "成交股數": int(r["_shares"]), "成交金額(元)": round(notional),
        "成交金額(萬)": round(notional / 1e4, 2),
        "進場價": round(float(r["entry"]), 2), "前收": round(float(r["prev_close"]), 2),
        "開盤原始gap%": round(float(r["raw_gap"]) * 100, 2), "調整後gap%": round(float(r["adj_gap"]) * 100, 2),
        "大盤開盤gap%": round(float(r["market_ret"]) * 100, 2),
        "漲停價": round(float(r["lu"]), 2), "跌停價": round(float(r["ld"]), 2),
        "進場距漲停%": round(float(r["zt_dist"]) * 100, 2),
        "日高": round(float(r["day_high"]), 2), "日低": round(float(r["day_low"]), 2), "收盤": round(float(r["day_close"]), 2),
        "停損價": round(slp, 2), "停利價": round(tpp, 2), "停利TP%": round(float(r["tp"]) * 100, 1),
        "停損價(回測連續價)": round(sl_raw, 3), "停利價(回測連續價)": round(tp_raw, 3),
        "價位需取整": bool(abs(slp - sl_raw) > 1e-9 or abs(tpp - tp_raw) > 1e-9),
        "盈虧(元)回測連續價": round(notional * (gross_raw - 2 * COST)),
        "出場價": round(ex, 2), "出場原因": reason,
        "毛損益%": round(gross * 100, 2), "淨損益%": round(net * 100, 2), "盈虧(元)": round(notional * net),
        "模型分位pred_q": round(float(r["pred_q"]), 3), "TP分位q1": round(float(r["q1"]), 3),
        "基礎倉位%": round(float(r["base_pos"]) * 100, 1), "實際權重%": round(float(r["_weight"]) * 100, 3),
        "ZT倍數": float(r["_zm"]), "30日倍數": round(float(r["_kT"]), 3), "淨值回撤倍數": float(r["_rs"]),
        "當日成交股數": dv, "當日成交額(萬)": round(dto / 1e4, 1) if np.isfinite(dto) else np.nan,
        "我占當日量%": round(r["_shares"] / dv * 100, 3) if np.isfinite(dv) and dv > 0 else np.nan,
        "我占當日額%": round(notional / dto * 100, 3) if np.isfinite(dto) and dto > 0 else np.nan,
        "曾觸漲停": bool(r["day_high"] >= r["lu"] - 1e-9) if r["direction"] == "SHORT" else bool(r["day_low"] <= r["ld"] + 1e-9),
        "開盤鎖死": bool(r["entry"] >= r["lu"] - 1e-9) if r["direction"] == "SHORT" else bool(r["entry"] <= r["ld"] + 1e-9),
        "整天鎖死": bool(abs(float(r["day_high"]) - float(r["day_low"])) < 1e-9),
        "注意": ("!我占當日成交額 >3%，會有衝擊成本" if (np.isfinite(dto) and dto > 0 and notional / dto > 0.03) else ""),
    })
T = pd.DataFrame(rows).sort_values(["日期", "序"]).reset_index(drop=True)
day = T.groupby("日期")["盈虧(元)"].sum()
bal = a.capital + day.cumsum()
T["當日總盈虧(元)"] = T["日期"].map(day.round(0))
T["累計現金(元)"] = T["日期"].map(bal.round(0))
os.makedirs(os.path.dirname(a.out), exist_ok=True)
T.to_csv(a.out, index=False, encoding="utf-8-sig")
print("wrote", a.out, len(T), "rows")
print("開盤鎖死筆數(应为0):", int(T["開盤鎖死"].sum()), " 整天鎖死:", int(T["整天鎖死"].sum()))
print("期間: %s ~ %s  筆數 %d  交易日 %d" % (T["日期"].min(), T["日期"].max(), len(T), T["日期"].nunique()))
print("起始 %.0f  期末 %.0f  盈虧 %.0f 元 (%.2f%%)" % (a.capital, bal.iloc[-1], bal.iloc[-1] - a.capital,
      (bal.iloc[-1] / a.capital - 1) * 100))
print("勝率 %.1f%%  平均淨損益 %.3f%%  最差單筆 %.2f%%" %
      ((T["盈虧(元)"] > 0).mean() * 100, T["淨損益%"].mean(), T["淨損益%"].min()))
print("出場原因:", T["出場原因"].value_counts().to_dict())
d = T["盈虧(元)"] - T["盈虧(元)回測連續價"]
print("價位需取整: %d / %d 筆 (%.1f%%)" % (int(T["價位需取整"].sum()), len(T), int(T["價位需取整"].sum()) / len(T) * 100))
print("取整後 vs 回測連續價: 總損益差 %.0f 元 (%.4f%%)  最大單筆差 %.0f 元" %
      (d.sum(), d.sum() / T["盈虧(元)回測連續價"].sum() * 100, d.abs().max()))
print("我占當日額百分比 最大 %.3f  中位 %.3f" % (T["我占當日額%"].max(), T["我占當日額%"].median()))
mm = T.assign(m=T["日期"].str[:7]).groupby("m").agg(筆數=("盈虧(元)", "size"), 盈虧=("盈虧(元)", "sum"),
                                                    勝率=("盈虧(元)", lambda x: (x > 0).mean() * 100))
mm["報酬%"] = mm["盈虧"] / a.capital * 100
print(mm.to_string(float_format=lambda v: "%.1f" % v))
T.to_pickle("_dt_T.pkl"); cv.to_pickle("_dt_cv.pkl")
