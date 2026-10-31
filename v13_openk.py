"""k = open_value / dv1, the constant that turns a T-1 figure into what will
actually be tradeable at the open.

At 09:00 the only legal input is yesterday's dollar turnover. The opening value is
share_09:00 * day_value, and day_value = ratio * dv1. Both multipliers were
measured; the product per order is what k should be, not the product of the two
medians (that understates it because the two are correlated - names that gap also
trade more and concentrate more at the open).

Usage: python v13_openk.py
"""
import os, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from min_bars import curve

OUT = r"D:\AI專案\StockAgent\DayTrading"
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
R = pd.read_csv(os.path.join(OUT, "fill_cost.csv"))
R["code"] = R["code"].astype(str).str.zfill(4)

rows = []
for _, r in R.iterrows():
    d = r["date"]; code = r["code"]
    if code not in TO1.columns or pd.Timestamp(d) not in TO1.index:
        continue
    dv1 = float(TO1.at[pd.Timestamp(d), code])
    if not np.isfinite(dv1) or dv1 <= 0:
        continue
    c = curve(code, d)
    if c is None or c[0]["09:00"] <= 0:
        continue
    openv = c[1] * c[0]["09:00"]
    rows.append((d, code, dv1, openv, openv / dv1, r["part"], r["cost"], r["stale"]))
K = pd.DataFrame(rows, columns=["date", "code", "dv1", "openv", "k", "part", "cost", "stale"])
K.to_csv(os.path.join(OUT, "open_k.csv"), index=False, encoding="utf-8-sig")

print("可算 %d 筆" % len(K))
print("k = 開盤可成交額 / T-1 成交額")
for q in (5, 10, 25, 50, 75, 90, 95):
    print("  p%-3d %.4f" % (q, np.percentile(K["k"], q)))
print("  平均 %.4f   加權(按 openv) %.4f" % (K["k"].mean(), np.average(K["k"], weights=K["openv"])))
print()
print("用 p50 還是用保守值？k 的左尾決定會不會低估風險：")
print("  用 k=p50 %.4f 時，實際 k 低於它的比例 %.1f%%" %
      (np.percentile(K["k"], 50), (K["k"] < np.percentile(K["k"], 50)).mean() * 100))
print()
print("預測參與率（用 k=p50）vs 實際參與率的一致性：")
kp = np.percentile(K["k"], 50)
pred = K["part"] * K["k"] / kp   # part_actual * (k_actual/k_assumed) = notional/(kp*dv1)
print("  corr %.3f   平均預測誤差 %+.3f%%   預測/實際 的中位 %.3f" %
      (pred.corr(K["part"]), (pred - K["part"]).mean() * 100, (pred / K["part"]).median()))
print("  用預測值分組的實際成本（這就是 live 能控制的東西）")
bins = [0, 0.02, 0.05, 0.10, 0.20, 10.0]
tmp = K.copy(); tmp["predb"] = pd.cut(pred, bins)
g = tmp[tmp["stale"] == False].groupby("predb", observed=True).agg(
    n=("cost", "size"), mean=("cost", "mean"), actual=("part", "median"))
for idx, r in g.iterrows():
    print("    預測 %-14s n=%4d  實際成本 %+7.3f%%  實際參與率中位 %6.2f%%" %
          (str(idx), int(r["n"]), r["mean"] * 100, r["actual"] * 100))
