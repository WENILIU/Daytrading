"""How much of the model's top-20 can a 4,500,000 whole-lot account actually place?

Two separate numbers per day, deliberately kept apart:
  survive = pass the two R9 gates (participation cap, 1-lot-too-big) ignoring cash.
          This is the size of the legal option set - it does not depend on capital
          being exhausted, so it isolates the structural filter.
  placed  = actually got an order, i.e. survive AND cash was still available in
          score order. This is what the trader would really have done.
Usage: python v13_top20_rate.py [--since 2026-01-01] [--until 2026-10-30]
"""
import argparse, os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import finlab
from finlab import data as fdata
from v13_engine import run_backtest, CAP0
import v13_sizing as S

ap = argparse.ArgumentParser()
ap.add_argument("--since", default="2026-01-01")
ap.add_argument("--until", default="2026-10-30")
ap.add_argument("--out", default=r"D:\AI專案\StockAgent\DayTrading")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
tok = __import__("re").search(r'FINLAB_TOKEN = "([^"]+)"', open("gap_fade_auto.py", encoding="utf-8").read()).group(1)
finlab.login(tok)

cv, got, _ = run_backtest(capture=(a.since, a.until), capital=CAP0,
                          kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
A = got["D"].copy()
A["stock"] = A["stock"].astype(str)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)

rows = []
for d, g in A.groupby("date"):
    g = g.sort_values("_rank")
    rem = CAP0
    n_top = min(20, len(g))
    survive = placed = placed_from_top = 0
    for _, r in g.iterrows():
        pr = float(r["entry"]); code = str(r["stock"]); rk = int(r["_rank"])
        dv1 = float(TO1.at[d, code]) if code in TO1.columns and d in TO1.index else np.nan
        free = S.lots_for(S.R9, float(r["_weight"]), pr, CAP0, dv1, capital=CAP0)
        real = S.lots_for(S.R9, float(r["_weight"]), pr, rem, dv1, capital=CAP0)
        if rk <= 20 and free > 0:
            survive += 1
        if real > 0:
            rem -= real * 1000.0 * pr
            placed += 1
            if rk <= 20:
                placed_from_top += 1
    rows.append({"日期": str(pd.Timestamp(d).date()), "訊號數": len(g), "前20名": n_top,
                 "前20通過閘門": survive, "前20存活率%": round(survive / n_top * 100, 1),
                 "實際下單筆數": placed, "其中來自前20": placed_from_top})
df = pd.DataFrame(rows)
p = os.path.join(a.out, "top20_survival_2026.csv")
df.to_csv(p, index=False, encoding="utf-8-sig")
print("wrote", p, len(df), "sessions")
print()
s = df["前20存活率%"]
print("top-20 survival rate over %d sessions:" % len(df))
for lo, hi in [(0, 10), (10, 25), (25, 50), (50, 75), (75, 100.01)]:
    n = int(((s >= lo) & (s < hi)).sum())
    print("  %3.0f%%<=x<%3.0f%% : %3d days %s" % (lo, min(hi, 100), n, "#" * (n // 2)))
print("  mean %.1f%%  median %.1f%%  p10 %.1f%%  p90 %.1f%%" %
      (s.mean(), s.median(), s.quantile(.1), s.quantile(.9)))
print("  days where NONE of the top-20 could be placed: %d" % int((df["前20通過閘門"] == 0).sum()))
print("  days where all 20 could be placed: %d" % int((df["前20通過閘門"] == 20).sum()))
print()
df["月"] = df["日期"].str[:7]
g = df.groupby("月").agg(交易日=("日期", "count"), 前20存活率均值=("前20存活率%", "mean"),
                       實際下單=("實際下單筆數", "mean"), 來自前20=("其中來自前20", "mean")).round(2)
print(g.to_string())
print()
print("worst 8 days:")
print(df.nsmallest(8, "前20存活率%")[["日期", "訊號數", "前20通過閘門", "前20存活率%", "實際下單筆數", "其中來自前20"]].to_string(index=False))
