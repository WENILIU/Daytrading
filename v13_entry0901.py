"""Enter at the open, or at 09:01? Same path, same exit engine, only the entry
price differs.

Why this is worth testing rather than assuming: RISK1 says the opening print is not
readable until 10-16s after 09:00:00, so "enter at the open" is not an available
action - it is a backtest convenience. And v13_fillcost.py measured that for the
median small SHORT order the price at the end of the first minute is 0.107% ABOVE
the opening print, i.e. a SHORT would be sold higher. Gap-fade picks names whose
opening print is an outlier, and the data says the outlier persists into the first
minute more often than it reverses inside it.

Isolation: both arms walk the SAME minute bars with the SAME exit logic (TP/SL
snapped to the price limit, force close at the 13:24 close). Only `entry` differs.
Any difference in PnL is therefore the entry price and nothing else.

Bars are START-labelled: the 09:00 bar's open is the exchange opening print, which
matched the backtest entry on 1718/1718 orders. So arm OPEN starts its exit scan
at the 09:00 bar, arm AT0901 at 09:01.

Usage: python v13_entry0901.py
"""
import os, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from v13_engine import CAP0, snap_price
import v13_sizing as S
from v13_engine import run_backtest
from min_bars import bars_for

SLO = 0.06
ORDER_CAP = 30
CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
_, got, _ = run_backtest(capture=("2023-01-01", "2026-12-31"), capital=CAP0, **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
rule = {k: v for k, v in S.R9.items() if k != "min_turnover_factor"}
rule["min_turnover_factor"] = 0.5


def walk(bars, entry, direction, lu, ld, tick, tp):
    """First touch of TP or SL over the minute path, else the 13:24 close.

    Within the entry bar the high/low are used too - a stop can be hit in the same
    minute the position is opened. SL is capped by the price limit exactly as the
    live script does, so a name pinned at the limit cannot lose more than the gap
    to it.
    """
    if direction == "SHORT":
        tpp = snap_price(entry * (1 - tp))
        slp = min(snap_price(entry * (1 + SLO)), round(lu - tick, 2))
        for t, o, h, l, c in bars:
            if t <= "09:00":
                continue
            if l <= tpp:
                return tpp, "TP"
            if h >= slp:
                return slp, "SL"
    else:
        tpp = snap_price(entry * (1 + tp))
        slp = max(snap_price(entry * (1 - SLO)), round(ld + tick, 2))
        for t, o, h, l, c in bars:
            if t <= "09:00":
                continue
            if h >= tpp:
                return tpp, "TP"
            if l <= slp:
                return slp, "SL"
    return bars[-1][4], "FC"


rows = []
for d, g in D.groupby("date"):
    g = g.sort_values("_rank"); rem = CAP0; n_day = 0
    day = str(pd.Timestamp(d).date())
    for _, r in g.iterrows():
        if n_day >= ORDER_CAP:
            break
        pr = float(r["entry"]); code = str(r["stock"])
        dv1 = float(TO1.at[d, code]) if (code in TO1.columns and d in TO1.index) else np.nan
        n = S.lots_for(rule, float(r["_weight"]), pr, rem, dv1, capital=CAP0)
        if n <= 0:
            continue
        rem -= n * 1000.0 * pr; n_day += 1
        bs = bars_for(code, day)
        if not bs:
            continue
        path = []
        for b in bs:
            t = b[0][11:16]
            if "09:00" <= t <= "13:24":
                path.append((t, b[2], b[4], b[5], b[3]))   # time, open, high, low, close
        if len(path) < 10:
            continue
        path.sort()
        e0 = path[0][1]                      # the exchange opening print
        e1 = path[0][4]                      # close of the 09:00 bar = price at ~09:01
        if not e0 or not e1 or e0 <= 0:
            continue
        lu = float(r["lu"]); ld = float(r["ld"]); tk = float(r["tick"]); tp = float(r["tp"])
        dr = r["direction"]
        x0, why0 = walk(path, e0, dr, lu, ld, tk, tp)
        x1, why1 = walk(path, e1, dr, lu, ld, tk, tp)
        sgn = -1.0 if dr == "SHORT" else 1.0
        rows.append((day, code, dr, n * 1000.0 * e0, e0, e1,
                     sgn * (x0 - e0) / e0, sgn * (x1 - e1) / e1, why0, why1))

R = pd.DataFrame(rows, columns=["date", "code", "dir", "notional", "open", "e0901",
                                "pnl_open", "pnl_0901", "why_open", "why_0901"])
R.to_csv(r"D:\AI專案\StockAgent\DayTrading\entry_0901.csv", index=False, encoding="utf-8-sig")
print("可比對的訂單：%d 筆（同一分鐘路徑、同一出場邏輯）" % len(R))
print()
print("每筆毛損益（未扣成本）")
for col, lbl in (("pnl_open", "進場=開盤價（回測假設）"), ("pnl_0901", "進場=09:01 價格")):
    a = R[col] * 100
    print("  %-22s 平均 %+6.3f%%  p50 %+6.3f%%  勝率 %5.1f%%  最差 %+6.2f%%" %
          (lbl, a.mean(), np.percentile(a, 50), (a > 0).mean() * 100, a.min()))
diff = (R["pnl_0901"] - R["pnl_open"]) * 100
print()
print("差額（09:01 減 開盤價）：平均 %+.4f%%  p50 %+.4f%%  09:01 較好的比例 %.1f%%" %
      (diff.mean(), np.percentile(diff, 50), (diff > 0).mean() * 100))
print()
for dr in ("SHORT", "LONG"):
    a = R[R["dir"] == dr]
    dd = (a["pnl_0901"] - a["pnl_open"]) * 100
    print("  %-6s n=%4d  開盤進場 %+6.3f%%   09:01 進場 %+6.3f%%   差 %+.4f%%" %
          (dr, len(a), a["pnl_open"].mean() * 100, a["pnl_0901"].mean() * 100, dd.mean()))
print()
print("出場原因分布（兩臂應該接近，差太多代表入場價改變了觸發順序）")
print("  開盤進場:", R["why_open"].value_counts().to_dict())
print("  09:01進場:", R["why_0901"].value_counts().to_dict())
