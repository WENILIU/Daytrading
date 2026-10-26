"""Generate the per-trade live plan for a date window at a fixed account size.

Writes two files:
  daytrading.csv                 every order a 4,500,000 account would actually place
                                 (whole lots, no margin), with a running cash balance
  daytrading_all_signals.csv     every signal the model asked for, including the ones
                                 450 万 cannot place, with the reason

Every field the audit charts annotate is a column here, so a chart and a row can be
compared one to one.
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
ap.add_argument("--sizing", default="r6", choices=["r6", "floor"],
                help="r6 = adopted live rule (cap per trade + skip coarse lots); "
                     "floor = the old floor-only view reproduced from the engine")
ap.add_argument("--max-per-trade", type=float, default=1_000_000)
ap.add_argument("--max-lot-value", type=float, default=250_000)
ap.add_argument("--max-dv1-frac", type=float, default=None,
                    help="cap one trade at this fraction of the name's T-1 turnover")
ap.add_argument("--min-range", type=float, default=0.001)
ap.add_argument("--out", default=OUT)
a = ap.parse_args()

cv, got, _ = run_backtest(capture=(a.since, a.until), capital=a.capital,
                          min_weight=a.min_weight, kmode="one", tmode="on",
                          min_range=a.min_range)
# D = raw design intent (every signal with a target weight, before any cash or
# whole-lot constraint). A is itself filtered by the design view's own cash loop, so
# it is NOT a faithful "what did the model want" list - 272 of the 750-odd orders a
# 4.5M account places are missing from it. C is what 450 万 can actually place.
A = got["D"]; C = got["C"]
designA = set((str(pd.Timestamp(d).date()), str(x)) for d, x in zip(got["A"]["date"], got["A"]["stock"]))
print("captured rows:", len(C), "days:", cv.loc[a.since:a.until].shape[0])

import finlab
from finlab import data as fdata
tok = re.search(r'FINLAB_TOKEN = "([^"]+)"', open("gap_fade_auto.py", encoding="utf-8").read()).group(1)
finlab.login(tok)
# T-1 dollar turnover: the only impact proxy that exists at 09:00 (T is not traded yet)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
vol = pd.DataFrame(fdata.get("price:成交股數"))
turn = pd.DataFrame(fdata.get("price:成交金額"))
vol.index = pd.to_datetime(vol.index); turn.index = pd.to_datetime(turn.index)

# what the 450M account actually placed, keyed so the design rows can be marked
placed = {(str(pd.Timestamp(r["date"]).date()), str(r["stock"])): r for _, r in C.iterrows()}
DAYCTX = {str(pd.Timestamp(d).date()): (float(r["n_signals"]), float(r["cdd"]), float(r["rs"]),
                                        float(r["market_ret"]), float(r["A_pnl"]), float(r["C_pnl"]),
                                        float(r["A_expo"]), float(r["C_expo"]))
          for d, r in cv.iterrows()}

cur_day = None; left = a.capital

rows = []
for _, r in A.iterrows():
    d = pd.Timestamp(r["date"])
    ds = str(d.date())
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
    # --- sizing: which lots this account would actually place ---
    if ds != cur_day:
        cur_day = ds; left = a.capital
    lot = pr * 1000.0
    # T-1 turnover must be resolved BEFORE sizing: the per-trade cap below uses it
    dv1 = float(TO1.at[d, code]) if code in TO1.columns and d in TO1.index else np.nan
    need = float(r["_weight"]) * a.capital
    if a.sizing == "r6":
        # R6 (adopted for live, see STRATEGY.md s2 sizing lab): cap the notional of a
        # single trade, skip names whose 1-lot value is coarser than any sensible
        # target, then floor to whole lots. Same rule as v13_sizing_lab.py rule R6.
        if lot > a.max_lot_value:
            sh = 0.0; notional = 0.0
            status = "跳過:1張市值過高(1張=%.1f 萬 > %.1f 萬)" % (lot / 1e4, a.max_lot_value / 1e4)
        else:
            tgt = min(need, a.max_per_trade)
            if a.max_dv1_frac is not None and np.isfinite(dv1) and dv1 > 0:
                tgt = min(tgt, a.max_dv1_frac * dv1)
            n = int(tgt // lot)
            if n < 1:
                sh = 0.0; notional = 0.0
                status = "跳過:整張不足(需 %.1f 萬, 1張=%.1f 萬)" % (tgt / 1e4, lot / 1e4)
            elif n * lot > left + 1e-9:
                n = int(left // lot)
                if n < 1:
                    sh = 0.0; notional = 0.0
                    status = "跳過:當日資金已滿"
                else:
                    sh = n * 1000.0; notional = sh * pr
                    status = "可下(縮量:當日現金已滿)"
            else:
                sh = n * 1000.0; notional = sh * pr
                status = "可下"
            if sh > 0:
                left -= notional
    else:  # floor-only view: take whatever the engine C mode actually placed
        hit = placed.get((ds, code))
        if hit is not None:
            sh = float(hit["_shares"]); notional = float(hit["_notional"])
            # the engine floors the design weight to whole lots; anything below that floor
            # was cut by the day's remaining cash, which is what "縮量" is meant to flag
            want = float(int(float(r["_weight"]) * a.capital / (pr * 1000)) * 1000)
            status = "可下" if sh >= want - 1e-9 else "可下(縮量:當日現金已滿)"
        else:
            sh = 0.0; notional = 0.0
            need = float(r["_weight"]) * a.capital; lot = pr * 1000
            status = ("跳過:整張不足(需 %.1f 萬, 1張=%.1f 萬)" % (need / 1e4, lot / 1e4)
                      if lot > need else "跳過:當日資金已滿")
    dv = float(vol.at[d, code]) if code in vol.columns and d in vol.index else np.nan
    dto = float(turn.at[d, code]) if code in turn.columns and d in turn.index else np.nan
    ns, cdd, rs, mret, apnl, cpnl, aexpo, cexpo = DAYCTX.get(ds, (np.nan,) * 8)
    rows.append({
        "日期": ds, "序": int(r["_rank"]), "股票": code, "方向": r["direction"], "狀態": status,
        "設計面有下": bool((ds, code) in designA),
        "成交張數": int(sh / 1000), "成交股數": int(sh), "成交金額(元)": round(notional),
        "成交金額(萬)": round(notional / 1e4, 2),
        "進場價": round(pr, 2), "開盤價": round(pr, 2), "前收": round(float(r["prev_close"]), 2),
        "開盤原始gap%": round(float(r["raw_gap"]) * 100, 2), "調整後gap%": round(float(r["adj_gap"]) * 100, 2),
        "大盤開盤gap%": round(mret * 100, 2),
        "漲停價": round(lu, 2), "跌停價": round(ld, 2),
        "進場距漲停%": round(float(r["zt_dist"]) * 100, 2),
        "日高": round(float(r["day_high"]), 2), "日低": round(float(r["day_low"]), 2),
        "收盤": round(float(r["day_close"]), 2),
        "停損價": round(slp, 2), "停利價": round(tpp, 2),
        "停損SL%": round(abs(slp - pr) / pr * 100, 2), "停利TP%": round(tpv * 100, 1),
        "停損價(回測連續價)": round(sl_raw, 3), "停利價(回測連續價)": round(tp_raw, 3),
        "價位需取整": bool(abs(slp - sl_raw) > 1e-9 or abs(tpp - tp_raw) > 1e-9),
        "出場價": round(ex, 2), "出場原因": reason,
        "毛損益%": round(gross * 100, 2), "淨損益%": round(net * 100, 2), "盈虧(元)": round(notional * net),
        "盈虧(元)回測連續價": round(notional * (gross_raw - 2 * COST)),
        "模型分位pred_q": round(float(r["pred_q"]), 3), "TP分位q1": round(float(r["q1"]), 3),
        "基礎倉位%": round(float(r["base_pos"]) * 100, 1), "設計權重%": round(float(r["_weight"]) * 100, 3),
        "實際權重%": round(notional / a.capital * 100, 3),
        "ZT倍數": float(r["_zm"]), "30日倍數": round(float(r["_kT"]), 3), "淨值回撤倍數": float(r["_rs"]),
        "當日訊號數": ns, "當日淨值回撤%": round(cdd * 100, 2) if np.isfinite(cdd) else np.nan,
        "當日設計曝險%": round(aexpo * 100, 1), "當日450萬曝險%": round(cexpo * 100, 1),
        "當日設計面pnl%": round(apnl * 100, 3), "當日450萬pnl%": round(cpnl * 100, 3),
        "當日成交股數": dv, "當日成交額(萬)": round(dto / 1e4, 1) if np.isfinite(dto) else np.nan,
        "我占當日量%": round(sh / dv * 100, 3) if np.isfinite(dv) and dv > 0 and sh > 0 else np.nan,
        "我占當日額%": round(notional / dto * 100, 3) if np.isfinite(dto) and dto > 0 and sh > 0 else np.nan,
        "我占T-1額%": round(notional / dv1 * 100, 3) if np.isfinite(dv1) and dv1 > 0 and sh > 0 else np.nan,
        "曾觸漲停": bool(r["day_high"] >= r["lu"] - 1e-9) if r["direction"] == "SHORT" else bool(r["day_low"] <= r["ld"] + 1e-9),
        "開盤鎖死": bool(r["entry"] >= r["lu"] - 1e-9) if r["direction"] == "SHORT" else bool(r["entry"] <= r["ld"] + 1e-9),
        "整天鎖死": bool(abs(float(r["day_high"]) - float(r["day_low"])) < 1e-9),
        "注意": ("!我占當日成交額 >3%，會有衝擊成本" if (np.isfinite(dto) and dto > 0 and notional / dto > 0.03) else ""),
    })
ALL = pd.DataFrame(rows).sort_values(["日期", "序"]).reset_index(drop=True)
T = ALL[ALL["狀態"].str.startswith("可下")].reset_index(drop=True)
day = T.groupby("日期")["盈虧(元)"].sum()
bal = a.capital + day.cumsum()
T["當日總盈虧(元)"] = T["日期"].map(day.round(0))
T["累計現金(元)"] = T["日期"].map(bal.round(0))
os.makedirs(os.path.dirname(a.out), exist_ok=True)
T.to_csv(a.out, index=False, encoding="utf-8-sig")
ALL.to_csv(os.path.splitext(a.out)[0] + "_all_signals.csv", index=False, encoding="utf-8-sig")
print("sizing rule:", a.sizing, " max_per_trade=%.0f  max_lot_value=%.0f" %      (a.max_per_trade, a.max_lot_value))
print("wrote", a.out, len(T), "rows; and _all_signals.csv", len(ALL), "rows")
print("開盤鎖死筆數(应为0):", int(ALL["開盤鎖死"].sum()), " 整天鎖死:", int(ALL["整天鎖死"].sum()))
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
print("我占當日額%% 最大 %.3f  中位 %.3f   |  我占T-1額%% 最大 %.1f  p95 %.2f  中位 %.3f" %
      (T["我占當日額%"].max(), T["我占當日額%"].median(), T["我占T-1額%"].max(),
       T["我占T-1額%"].quantile(0.95), T["我占T-1額%"].median()))
print("單日最大虧 %.0f 元  單日最大賺 %.0f 元" % (day.min(), day.max()))
skip = ALL[~ALL["狀態"].str.startswith("可下")]
print("模型要的設計訊號 %d 筆；450 萬能下 %d 筆 (%.1f%%)，被跳過 %d 筆" %
      (len(ALL), len(T), len(T) / len(ALL) * 100, len(skip)))
reasons = skip["狀態"].str.split("(").str[0].value_counts()
print("跳過原因:", reasons.to_dict())
print("單筆名義 最大 %.1f 萬  平均 %.1f 萬  (上限 %.1f 萬)" %
      (T["成交金額(萬)"].max(), T["成交金額(萬)"].mean(), a.max_per_trade / 1e4))
assert T["成交金額(萬)"].max() * 1e4 <= a.max_per_trade + 1e-6, "per-trade cap violated"
if a.sizing == "r6":
    bad = int((T["進場價"] * 1000 > a.max_lot_value).sum())
    print("R6 檢查: 1張市值 > %.1f 萬 卻仍下單的筆數 = %d (应为 0)" % (a.max_lot_value / 1e4, bad))
    assert bad == 0
print("其中設計面(複利、無整張)會下的有 %d 筆 -> 450 萬與設計面的差距就是整張門檻造成的" %
      int(ALL["設計面有下"].sum()))
mm = T.assign(m=T["日期"].str[:7]).groupby("m").agg(筆數=("盈虧(元)", "size"), 盈虧=("盈虧(元)", "sum"),
                                                    勝率=("盈虧(元)", lambda x: (x > 0).mean() * 100))
mm["報酬%"] = mm["盈虧"] / a.capital * 100
print(mm.to_string(float_format=lambda v: "%.1f" % v))
T.to_pickle("_dt_T.pkl"); ALL.to_pickle("_dt_ALL.pkl"); cv.to_pickle("_dt_cv.pkl")
