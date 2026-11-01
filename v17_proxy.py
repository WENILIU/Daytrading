# -*- coding: utf-8 -*-
r"""Can a daily bar express the resting-order rule exactly?

The order in R2 is placed at entry and rests all day, so "did it fill" is just
"did the price trade at or below that level at any point today" - which is what
day_low says. If the daily test agrees with the minute path, the rule can go
into the daily-bar backtest with no calibration at all. If it does not agree,
the daily bar is over-counting fills and the integrated number would be fiction.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
import v13_target as T
from v13_engine import snap_price, SLO

df = pd.read_pickle("_min1_lock.pkl")


def binding(r):
    if r["direction"] == "SHORT":
        return round(r["lim"] - r["tick"], 2) < snap_price(r["entry"] * (1 + SLO)) - 1e-9
    return round(r["lim"] + r["tick"], 2) > snap_price(r["entry"] * (1 - SLO)) + 1e-9


df = df[df.apply(binding, axis=1)].copy()
key = list(zip([pd.Timestamp(x) for x in df["date"]], df["code"]))
sub = T.D.set_index([T.D["date"], T.D["stock"]])
day = {}
for k in set(key):
    try:
        r = sub.loc[k]
    except KeyError:
        continue
    if isinstance(r, pd.DataFrame):
        r = r.iloc[0]
    day[k] = (float(r["day_high"]), float(r["day_low"]), float(r["day_close"]))
df["dhi"] = [day.get(k, (np.nan,) * 3)[0] for k in key]
df["dlo"] = [day.get(k, (np.nan,) * 3)[1] for k in key]
df["dcl"] = [day.get(k, (np.nan,) * 3)[2] for k in key]
print("可比對：%d / %d 筆（日線面板查得到）" % (df["dlo"].notna().sum(), len(df)))
df = df[df["dlo"].notna()]
side = np.where(df["direction"] == "SHORT", 1.0, -1.0)

print("\n   X%   1分K成交   日線判定   一致   日線多判   日線少判")
for X in ("0.005", "0.010", "0.015", "0.020", "0.030"):
    trig = df["lim"] * (1 - side * float(X))
    m1 = (df["hit_" + X] != "").values
    dl = np.where(side > 0, df["dlo"].values <= trig + 1e-9, df["dhi"].values >= trig - 1e-9)
    print("  %4.1f%%   %4d      %4d     %4d     %4d       %4d"
          % (float(X) * 100, m1.sum(), dl.sum(), int((m1 == dl).sum()),
             int(((~m1) & dl).sum()), int((m1 & (~dl)).sum())))

print("\n鎖死判定（日線收盤在價限上 vs 1 分 K 13:25 在價限上）：")
lk1 = np.where(side > 0, df["close_1325"] >= df["lim"] - df["tick"] - 1e-9,
               df["close_1325"] <= df["lim"] + df["tick"] + 1e-9)
lk2 = np.where(side > 0, df["dcl"].values >= df["lim"] - df["tick"] - 1e-9,
               df["dcl"].values <= df["lim"] + df["tick"] + 1e-9)
print("   1分K %d  日線 %d  一致 %d" % (lk1.sum(), lk2.sum(), int((lk1 == lk2).sum())))
