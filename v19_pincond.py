# -*- coding: utf-8 -*-
r"""Can the overnight cost of a pinned short be predicted in advance?

The previous run printed "0.1 pct get money back" because "%.1f%%" % x * 100 multiplies
the STRING, not the number. The real figure is 10 pct. So the question is not "does it
revert" (it almost never does) but "is the size of the loss, or the rare reversion,
predictable from information available at 09:00". If it is, the 3.149 pct the backtest
charges becomes conditional and the names that should never be shorted become identifiable.

Features are taken from the signal panel, which is by construction what was knowable at
09:00 on the trade date, plus the intraday path already recorded in _min1_lock.pkl.
"""
import warnings; warnings.filterwarnings("ignore")
import pickle, numpy as np, pandas as pd
import v13_target as T

df = pickle.load(open("_min1_lock.pkl", "rb"))
df["date"] = pd.to_datetime(df["date"].astype(str)); df["code"] = df["code"].astype(str)
d = df.dropna(subset=["nd_open", "close_1325"]).copy()
sh = d[d["direction"] == "SHORT"].copy()
sh["overnight"] = (sh["close_1325"] - sh["nd_open"]) / sh["entry"] * 100
pin = sh[sh["close_1325"] >= sh["lim"] - 1e-9].copy()
s = pin["overnight"]
print("=== 鎖死放空的隔夜成本 (n=%d) ===" % len(pin))
print("平均 %+0.3f%%   中位 %+0.3f%%" % (s.mean(), s.median()))
print("隔天開盤較便宜(還本): %d 筆 = %.1f%%" % ((s > 0).sum(), (s > 0).mean() * 100))
print("還本 >1%%: %.1f%%   虧 >5%%: %.1f%%   虧 >10%%: %.1f%%"
      % ((s > 1).mean() * 100, (s < -5).mean() * 100, (s < -10).mean() * 100))

key = T.D.set_index([T.D["date"], T.D["stock"].astype(str)])
feats = ["zt_close_60", "zt_close_20", "touch_rate_up_250", "vol_ratio", "dist_hi60",
         "ret_20", "gapup_60", "adj_gap", "gap_raw"]
have = [f for f in feats if f in key.columns]
pin = pin.join(key[have], on=["date", "code"], rsuffix="_panel")
print("\njoin 到 09:00 特徵:", len(pin[have].dropna(how="all")), "筆完全無特徵")
print("可用特徵欄位:", have)

def by(feature, q=3):
    x = pd.to_numeric(pin[feature], errors="coerce")
    ok = pin[x.notna()]
    if len(ok) < 60:
        return
    try:
        b = pd.qcut(x[ok.index], q, duplicates="drop")
    except ValueError:
        return
    g = ok.groupby(b, observed=True)["overnight"].agg(["size", "mean", "median",
                                                       lambda v: (v > 0).mean() * 100])
    g.columns = ["n", "mean", "median", "back_pct"]
    print("\n--- %s ---" % feature)
    for idx, r in g.iterrows():
        print("   %-26s n=%3d  平均 %+6.2f%%  中位 %+6.2f%%  還本 %4.1f%%"
              % (str(idx), int(r["n"]), r["mean"], r["median"], r["back_pct"]))

for f in have:
    by(f)
pin["tt"] = pd.to_datetime(pin["touch_time"], errors="coerce")
ok = pin[pin["tt"].notna()].copy()
ok["tm"] = ok["tt"].dt.hour * 60 + ok["tt"].dt.minute
for lab, lo, hi in [("09:00-09:30 觸及", 540, 570), ("09:30-11:00", 570, 660),
                    ("11:00-13:00", 660, 780), ("13:00 以後", 780, 900)]:
    m = ok[(ok["tm"] >= lo) & (ok["tm"] < hi)]["overnight"]
    if len(m):
        print("   觸及漲停 %-14s n=%3d  平均 %+6.2f%%  中位 %+6.2f%%  還本 %4.1f%%"
              % (lab, len(m), m.mean(), m.median(), (m > 0).mean() * 100))
pin.to_csv("_pinnext_detail.csv", index=False)
print("\nsaved _pinnext_detail.csv")

