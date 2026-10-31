"""Measure the entry slippage the backtest assumes away. See v13_slippage.py header.

Usage: python v13_slip_calc.py
"""
import os, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from min_bars import open_ticks

OUT = r"D:\AI專案\StockAgent\DayTrading"
O = pd.read_csv(os.path.join(OUT, "slip_orders.csv"))
O["code"] = O["code"].astype(str).str.zfill(4)

rows = []; bad_px = 0; no_open = 0
for _, r in O.iterrows():
    t = open_ticks(r["code"], r["date"])
    if t is None:
        no_open += 1
        continue
    op, f60, f120 = t
    if op is None or f60 is None or op <= 0:
        no_open += 1
        continue
    # the backtest entry must be the same print the corpus calls the open, or the
    # two are describing different markets and nothing below means anything
    if abs(op - r["entry_bt"]) > 0.005 * max(op, 1.0):
        bad_px += 1
    sgn = 1.0 if r["dir"] == "LONG" else -1.0
    # cost > 0 means we would have paid to be late: LONG buys higher, SHORT sells lower
    c60 = sgn * (f60 - op) / op
    c120 = sgn * (f120 - op) / op if f120 else np.nan
    rows.append((r["date"], r["code"], r["dir"], r["notional"], op, f60, f120, c60, c120))

R = pd.DataFrame(rows, columns=["date", "code", "dir", "notional", "open", "f60", "f120", "cost60", "cost120"])
R.to_csv(os.path.join(OUT, "slip_measured.csv"), index=False, encoding="utf-8-sig")
print("可算的訂單 %d / %d；開盤無成交 %d；開盤價與回測 entry 不符 %d（%.2f%%）" %
      (len(R), len(O), no_open, bad_px, bad_px / max(len(R), 1) * 100))
print()
print("進場滑價成本（正值 = 比開盤價差，即延遲造成的代價）")
print("  口徑                    n      p10      p50      p90     平均     加權平均")
for col, lbl in (("cost60", "延遲到 ~60 秒（保守）"), ("cost120", "延遲到 ~120 秒（更差）")):
    q = R[col].dropna() * 100
    w = np.average(R[col].dropna() * 100, weights=R.loc[q.index, "notional"]) if len(q) else np.nan
    print("  %-22s %5d  %6.2f%%  %6.2f%%  %6.2f%%  %6.2f%%  %7.2f%%" %
          (lbl, len(q), np.percentile(q, 10), np.percentile(q, 50), np.percentile(q, 90),
           q.mean(), w))
print()
print("分方向（這是重點：兩個方向都要付，因為策略挑的就是開盤極端價）")
for dr in ("SHORT", "LONG"):
    q = R[R["dir"] == dr]["cost60"].dropna() * 100
    print("  %-6s n=%4d  p50 %+6.3f%%  p90 %+6.2f%%  平均 %+6.3f%%  付錢的比例 %5.1f%%" %
          (dr, len(q), np.percentile(q, 50), np.percentile(q, 90), q.mean(), (q > 0).mean() * 100))
print()
print("若把平均成本當成每筆固定扣費，等價於每邊幾個 bp：")
m = R["cost60"].dropna().mean() * 10000
print("  進場滑價 %.1f bp（只算進場，出場 13:25 是市價單另有滑價，未在此測量）" % m)
print("  現行成本常數每邊 %.1f bp -> 加上進場滑價後每邊應為 %.1f bp" % (0.111 * 100, 0.111 * 100 + m))
