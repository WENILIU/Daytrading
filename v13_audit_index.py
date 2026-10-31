"""Daily index for the day-by-day manual review.

One run_backtest call for the whole range, then per day apply the SAME live order
rule the trader uses (v13_sizing.R9: participation cap, 1-lot-too-big cap, whole
lots, running cash). Emits one row per session so the reviewer can pick which days
to open the full per-stock charts for, instead of generating thousands of images.

Usage: python v13_audit_index.py --since 2026-01-01 --until 2026-10-30
"""
import argparse, os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import finlab
from finlab import data as fdata
from v13_engine import run_backtest, stats, exit_of_legal, CAP0, COST
import v13_sizing as S

ap = argparse.ArgumentParser()
ap.add_argument("--since", default="2026-01-01")
ap.add_argument("--until", default="2026-10-30")
ap.add_argument("--out", default=r"D:\AI專案\StockAgent\DayTrading")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)

tok = __import__("re").search(r'FINLAB_TOKEN = "([^"]+)"', open("gap_fade_auto.py", encoding="utf-8").read()).group(1)
finlab.login(tok)

cv, got, _ = run_backtest(capture=(a.since, a.until), capital=CAP0, **CFG)
A = got["D"].copy()
A["stock"] = A["stock"].astype(str)
print("design intents: %d over %d sessions" % (len(A), A["date"].nunique()))

TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
turn = pd.DataFrame(fdata.get("price:成交金額"))
turn.index = pd.to_datetime(turn.index)

rows = []
for d, g in A.groupby("date"):
    g = g.sort_values("_rank")
    rem = CAP0
    n_ok = 0; expo = 0.0; yuan = 0.0; pnl_w = 0.0
    n_short = n_long = 0
    reasons = {}
    for _, r in g.iterrows():
        pr = float(r["entry"]); pos = float(r["_weight"]); code = str(r["stock"])
        dv1 = float(TO1.at[d, code]) if code in TO1.columns and d in TO1.index else np.nan
        ex, slp, tpp, reason, gross = exit_of_legal(
            r["direction"], pr, float(r["day_high"]), float(r["day_low"]), float(r["day_close"]),
            float(r["lu"]), float(r["ld"]), float(r["tick"]), float(r["tp"]))
        n = S.lots_for(S.R9, pos, pr, rem, dv1, capital=CAP0)
        if n <= 0:
            why = S.skip_reason(S.R9, pos, pr, dv1, capital=CAP0) or "資金已滿"
            reasons[why] = reasons.get(why, 0) + 1
            continue
        sh = n * 1000.0
        net = gross - 2 * COST
        rem -= sh * pr
        expo += sh * pr
        yuan += sh * pr * net
        pnl_w += sh * pr * net
        n_ok += 1
        if r["direction"] == "SHORT":
            n_short += 1
        else:
            n_long += 1
    dto = 0.0
    try:
        dto = float(turn.loc[pd.Timestamp(d)].sum())
    except Exception:
        pass
    top = sorted(reasons.items(), key=lambda kv: -kv[1])
    row = cv.loc[pd.Timestamp(d)]
    rows.append({
        "日期": str(pd.Timestamp(d).date()),
        "大盤開盤gap%": round(float(row["market_ret"]) * 100, 2),
        "訊號數": int(row["n_signals"]),
        "R9可下筆數": n_ok, "R9做多": n_long, "R9放空": n_short,
        "R9曝險%": round(expo / CAP0 * 100, 1),
        "R9當日%": round(yuan / CAP0 * 100, 3),
        "R9當日元": round(yuan),
        "引擎C筆數": int(row["C_n"]), "引擎C當日%": round(float(row["C_pnl"]) * 100, 3),
        "設計A筆數": int(row["A_n"]), "設計A當日%": round(float(row["A_pnl"]) * 100, 3),
        "淨值回撤%": round(float(row["cdd"]) * 100, 2),
        "市場當日成交額(億)": round(dto / 1e9, 1) if dto > 0 else np.nan,
        "跳過原因筆數": "; ".join("%s:%d" % (k, v) for k, v in top[:3]),
    })
idx = pd.DataFrame(rows).sort_values("日期").reset_index(drop=True)
idx["R9累計元"] = idx["R9當日元"].cumsum().round()
p = os.path.join(a.out, "daily_index_%s_%s.csv" % (a.since.replace("-", ""), a.until.replace("-", "")))
idx.to_csv(p, index=False, encoding="utf-8-sig")
print("wrote", p, len(idx), "rows")

r9 = idx["R9當日%"] / 100.0
eng = idx["引擎C當日%"] / 100.0
des = idx["設計A當日%"] / 100.0
for nm, s in (("R9 現行下單規則", r9), ("引擎 allocate", eng), ("設計面 A", des)):
    eq = (1 + s).cumprod()
    n = len(s)
    yrs = n / 244.0
    cagr = (eq.iloc[-1] ** (1 / yrs) - 1) * 100 if yrs > 0 else np.nan
    mdd = ((eq / eq.cummax()) - 1).min() * 100
    shp = s.mean() / s.std() * np.sqrt(244) if s.std() > 0 else np.nan
    print("%-18s 筆數/日 %5.1f  期間報酬 %8.1f%%  CAGR %8.1f%%  MDD %6.2f%%  Sharpe %5.2f" %
          (nm, idx["R9可下筆數"].mean() if nm.startswith("R9") else np.nan,
           (eq.iloc[-1] - 1) * 100, cagr, mdd, shp))
print("total R9 yuan:", round(idx["R9當日元"].sum()))
