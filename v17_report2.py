# -*- coding: utf-8 -*-
r"""Corrected limit-lock analysis.

v17_report.py ran on the 3,934 trades that exit_of_legal LABELED as limit touches.
That label was wrong: it tested slp < entry*(1+SLO), and snap_price rounds to the
nearest legal price, so an ordinary 4% stop fell below its own trigger about half
the time and was counted as a limit touch. Fixed in v13_engine.py the same day.
The real count is 583, of which 105 are limit-up stops on shorts.

_min1_lock.pkl still holds the minute-path outcomes for the superset, and for a
genuine limit-bound stop slp is identical under the old and the new label (only
the string changed), so the cached paths are valid for the corrected subset.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
from v13_engine import snap_price, SLO

CAP = 4_500_000.0
STOPS = pd.DataFrame([dict(date=str(a), code=str(b), direction=c, reason=d,
                           notional=float(e), gross=f) for a, b, c, d, e, f
                      in pd.read_pickle("_min1_all_stops.pkl")])
PATH = pd.read_pickle("_min1_lock.pkl")
print("修正後真實觸價限停損：%d 筆（SHORT %d / LONG %d）"
      % (len(STOPS), (STOPS["direction"] == "SHORT").sum(), (STOPS["direction"] == "LONG").sum()))

# keep only rows where the price limit really is the binding stop
def binding(r):
    if r["direction"] == "SHORT":
        return round(r["lim"] - r["tick"], 2) < snap_price(r["entry"] * (1 + SLO)) - 1e-9
    return round(r["lim"] + r["tick"], 2) > snap_price(r["entry"] * (1 - SLO)) + 1e-9
PATH["binding"] = PATH.apply(binding, axis=1)
df = PATH[PATH["binding"]].copy()
print("其中有 1 分 K 路徑可查：%d 筆（%.1f%%）" % (len(df), len(df) / len(STOPS) * 100))
if not len(df):
    raise SystemExit(0)
df["year"] = [x[:4] for x in df["date"]]

# re-price with the limit-bound stop, which is what the shipped book does here
side = np.where(df["direction"] == "SHORT", 1.0, -1.0)
df["slp_true"] = np.where(side > 0, np.round(df["lim"] - df["tick"], 2), np.round(df["lim"] + df["tick"], 2))
df["r0"] = np.where(side > 0, (df["entry"] - df["slp_true"]) / df["entry"],
                    (df["slp_true"] - df["entry"]) / df["entry"])
df["r1"] = np.where(side > 0, (df["entry"] - df["close_1325"]) / df["entry"],
                    (df["close_1325"] - df["entry"]) / df["entry"])
for X in ("0.005", "0.010", "0.015", "0.020", "0.030"):
    trig = df["lim"] * (1 - side * float(X))
    filled = (df["hit_" + X] != "").values
    px = np.where(filled, trig, df["slp_true"])
    df["r2_" + X] = np.where(side > 0, (df["entry"] - px) / df["entry"], (px - df["entry"]) / df["entry"])

w = df["notional"].values
base = float((df["r0"] * w).sum())
print("\n=== 同一批交易上比較（只計這批本身，未計資金提前釋放）===")
print("   R0 現行 觸價限即停損      合計 %+11.0f 元   加權平均 %+6.3f%%" % (base, base / w.sum() * 100))
r1 = float((df["r1"] * w).sum())
print("   R1 結在 13:25（上界）     合計 %+11.0f 元   加權平均 %+6.3f%%   差 %+9.0f 元 = %+.1f pp/整段"
      % (r1, r1 / w.sum() * 100, r1 - base, (r1 - base) / CAP * 100))
for X in ("0.005", "0.010", "0.015", "0.020", "0.030"):
    v = float((df["r2_" + X] * w).sum())
    f = int((df["hit_" + X] != "").sum())
    print("   R2 掛在價限下方 %5.1f%%    合計 %+11.0f 元   成交 %3d/%d   差 %+9.0f 元 = %+.1f pp/整段"
          % (float(X) * 100, v, f, len(df), v - base, (v - base) / CAP * 100))

print("\n=== 鎖死 vs 解開 ===")
print("   鎖到收盤 %d (%.1f%%)   曾解開 %d (%.1f%%)"
      % (df["locked"].sum(), df["locked"].mean() * 100, (~df["locked"]).sum(), (1 - df["locked"].mean()) * 100))
print("\n=== 逐年 ===")
for y, g in df.groupby("year"):
    gw = g["notional"].values
    b = float((g["r0"] * gw).sum())
    best = max(("r2_" + X for X in ("0.005", "0.010", "0.015", "0.020", "0.030")),
               key=lambda c: float((g[c] * gw).sum()))
    v = float((g[best] * gw).sum())
    print("   %s n=%3d  R0 %+9.0f  R2(%s) %+9.0f  差 %+8.0f 元 = %+.1f pp  鎖死 %.0f%%"
          % (y, len(g), b, best[3:], v, v - b, (v - b) / CAP * 100, g["locked"].mean() * 100))

print("\n=== 覆蓋率（能分析的 / 全部真實觸價限停損）===")
tot = STOPS["date"].str[:4].value_counts(); got = df["year"].value_counts()
for y in sorted(tot.index):
    print("   %s  %3d / %3d" % (y, got.get(y, 0), tot[y]))

print("\n=== 鎖死那批的隔天結果 ===")
lk = df[df["locked"] & df["nd_open"].notna()]
for dr in ("SHORT", "LONG"):
    s = lk[lk["direction"] == dr]
    if not len(s):
        continue
    sg = 1.0 if dr == "SHORT" else -1.0
    go = sg * (s["nd_open"] - s["lim"]) / s["lim"] * 100
    gc = sg * (s["nd_close"] - s["lim"]) / s["lim"] * 100
    print("   %s n=%3d  隔天開盤 中位 %+.2f%% p10 %+.2f%% 最差 %+.2f%% | 隔天收盤 中位 %+.2f%% p10 %+.2f%%"
          % (dr, len(s), go.median(), go.quantile(0.1), go.min(), gc.median(), gc.quantile(0.1)))
    print("        （正值對我們有利）若鎖死改到隔天開盤回補，金額影響 %+9.0f 元"
          % float((sg * (s["slp_true"] - s["nd_open"]) / s["entry"] * s["notional"]).sum()))
