"""Fill cost vs participation, with the stale-price explanation tested and removed.

v13_slip_calc.py measured a near-zero average entry slippage but +0.16% weighted,
and the cost rose with participation. Two explanations:
  impact    - a big order really does move a thin opening tape
  staleness - the 09:00 bar close is just the auction print repeated, so cost is
              zero by construction and the sample is dominated by uninformative rows
The second is testable: if the 09:00 bar has high == low, the only print in that
minute was the auction and the measured cost is meaningless. Drop those rows and
re-measure. Checked example: 2330 2025-09-01 09:00 bar is open 1150 / high 1155 /
low 1145 / close 1150 - a real two-sided minute that happened to round-trip, so
that one is NOT stale and does count.

Usage: python v13_fillcost.py
"""
import os, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from min_bars import open_ticks, curve

OUT = r"D:\AI專案\StockAgent\DayTrading"
O = pd.read_csv(os.path.join(OUT, "slip_orders.csv"))
O["code"] = O["code"].astype(str).str.zfill(4)

rows = []
for _, r in O.iterrows():
    t = open_ticks(r["code"], r["date"])
    if t is None:
        continue
    op, f60, f120, h0, l0 = t
    if not op or not f60 or op <= 0:
        continue
    c = curve(r["code"], r["date"])
    if c is None or c[0]["09:00"] <= 0:
        continue
    part = r["notional"] / (c[1] * c[0]["09:00"])
    sgn = 1.0 if r["dir"] == "LONG" else -1.0
    rows.append((r["date"], r["code"], r["dir"], r["notional"], op, f60, h0, l0,
                 h0 == l0, part, sgn * (f60 - op) / op))
R = pd.DataFrame(rows, columns=["date", "code", "dir", "notional", "open", "f60",
                                "h0", "l0", "stale", "part", "cost"])
R.to_csv(os.path.join(OUT, "fill_cost.csv"), index=False, encoding="utf-8-sig")

print("可測 %d 筆。其中 09:00 那根 high==low（只有競價、無連續成交）：%d 筆（%.1f%%）" %
      (len(R), R["stale"].sum(), R["stale"].mean() * 100))
print("  這些列的 cost 恆等於 0，是構造出來的，不是成交品質好。下面一律排除。")
print()
q = R[~R["stale"]].copy()
print("排除後 n=%d" % len(q))
print("  平均 cost %+.3f%%   加權 %+.3f%%   p50 %+.3f%%   p90 %+.2f%%" %
      (q["cost"].mean() * 100, np.average(q["cost"], weights=q["notional"]) * 100,
       np.percentile(q["cost"], 50) * 100, np.percentile(q["cost"], 90) * 100))
print()
bins = [0, 0.02, 0.05, 0.10, 0.20, 0.50, 10.0]
q["b"] = pd.cut(q["part"], bins)
print("成交品質 vs 參與率（分母 = 09:00 已成交額；正值 = 比開盤價差）")
print("  %-14s %5s %10s %10s %10s %9s" % ("參與率", "n", "平均", "p50", "p90", "單量合計"))
g = q.groupby("b", observed=True).agg(n=("cost", "size"), mean=("cost", "mean"),
                                      med=("cost", "median"),
                                      p90=("cost", lambda x: np.percentile(x, 90)),
                                      yuan=("notional", "sum"))
for idx, r in g.iterrows():
    print("  %-14s %5d %+9.3f%% %+9.3f%% %+9.2f%% %9s" %
          (str(idx), int(r["n"]), r["mean"] * 100, r["med"] * 100, r["p90"] * 100, "{:,.0f}".format(r["yuan"])))
print()
print("分方向（排除 stale 後）")
for dr in ("SHORT", "LONG"):
    a = q[q["dir"] == dr]["cost"] * 100
    print("  %-6s n=%4d 平均 %+6.3f%%  p50 %+6.3f%%  p90 %+6.2f%%  付錢比例 %5.1f%%" %
          (dr, len(a), a.mean(), np.percentile(a, 50), np.percentile(a, 90), (a > 0).mean() * 100))
print()
print("單量加權的總成本：%+.3f%%（這是把滑價當固定費會用的數字）" %
      (np.average(q["cost"], weights=q["notional"]) * 100))
