# -*- coding: utf-8 -*-
r"""Honest fill model for the limit-lock rule.

A buy order one tick under a locked limit-up sits behind the queue and does not
fill at all, so the shipped book's booked stop price is not an obtainable price
for the locked cases. Any comparison has to apply the same physics to both sides:

  locked at 13:25   -> cannot exit; the position carries to the next open.
  not locked        -> exit at whatever price is available.

Rules compared, all on the same 181 trades that have minute paths:
  R0  as booked   : exit at the limit-bound price. Optimistic for the locked ones.
  R0h honest      : locked -> next open, otherwise the booked price.
  R1  settle 13:25: locked -> next open, otherwise the 13:25 price. Upper bound
                    for "never stop at the limit".
  R2(X) rule      : at entry, when the stop is the limit-bound one, rest a LIMIT
                    order X pct back from the limit instead of stopping at it.
                    Fills only if the price comes back. Unfilled: locked -> next
                    open, otherwise the 13:25 price.

A resting limit order cannot fill worse than its price, which is why R2 is a rule
and not a hope. It is priced at the trigger level, the worst it can do.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
from v13_engine import snap_price, SLO

CAP = 4_500_000.0
XGRID = ("0.005", "0.010", "0.015", "0.020", "0.030")
STOPS = pd.DataFrame([dict(date=str(a), code=str(b), direction=c, notional=float(e))
                      for a, b, c, d, e, f in pd.read_pickle("_min1_all_stops.pkl")])
df = pd.read_pickle("_min1_lock.pkl")


def binding(r):
    if r["direction"] == "SHORT":
        return round(r["lim"] - r["tick"], 2) < snap_price(r["entry"] * (1 + SLO)) - 1e-9
    return round(r["lim"] + r["tick"], 2) > snap_price(r["entry"] * (1 - SLO)) + 1e-9


df["binding"] = df.apply(binding, axis=1)
df = df[df["binding"]].copy()
side = np.where(df["direction"] == "SHORT", 1.0, -1.0)
df["year"] = [x[:4] for x in df["date"]]
df["slp_true"] = np.where(side > 0, np.round(df["lim"] - df["tick"], 2), np.round(df["lim"] + df["tick"], 2))
# lock state at our exit time, not at the 13:30 close
df["lock25"] = np.where(side > 0, df["close_1325"] >= df["lim"] - df["tick"] - 1e-9,
                        df["close_1325"] <= df["lim"] + df["tick"] + 1e-9)
nd = df["nd_open"].fillna(df["close_1325"])


def ret(px):
    return np.where(side > 0, (df["entry"] - px) / df["entry"], (px - df["entry"]) / df["entry"])


df["R0"] = ret(df["slp_true"])
df["R0h"] = ret(np.where(df["lock25"], nd, df["slp_true"]))
df["R1"] = ret(np.where(df["lock25"], nd, df["close_1325"]))
for X in XGRID:
    trig = df["lim"] * (1 - side * float(X))
    filled = (df["hit_" + X] != "").values
    px = np.where(filled, trig, np.where(df["lock25"], nd, df["close_1325"]))
    df["R2" + X] = ret(px)

w = df["notional"].values
n = len(df)
span_years = (pd.to_datetime(df["date"]).max() - pd.to_datetime(df["date"]).min()).days / 365.25
print("樣本 %d 筆，%s ~ %s（%.1f 年），名義合計 %.0f 萬" % (n, df["date"].min(), df["date"].max(),
                                                          span_years, w.sum() / 1e6))
print("13:25 仍鎖在價限：%d 筆（%.1f%%）" % (df["lock25"].sum(), df["lock25"].mean() * 100))
print("方向：SHORT %d / LONG %d" % ((side > 0).sum(), (side < 0).sum()))

base_h = float((df["R0h"] * w).sum())
print("\n=== 同一批交易，含成交現實 ===")
for nm, col, note in [("R0  現行（帳面上）", "R0", "鎖死那批假裝能以價限內一檔成交，偏樂觀"),
                      ("R0h 現行（誠實）", "R0h", "鎖死改到隔天開盤回補")]:
    v = float((df[col] * w).sum())
    print("   %-20s %+11.0f 元   加權 %+6.3f%%   %s" % (nm, v, v / w.sum() * 100, note))
print()
for X in XGRID + ("",):
    col = "R1" if X == "" else "R2" + X
    v = float((df[col] * w).sum())
    lab = "R1  從不停在價限（上界）" if X == "" else "R2  掛在價限下方 %4.1f%%" % (float(X) * 100)
    extra = ""
    if X:
        extra = "   成交 %3d/%d" % (int((df["hit_" + X] != "").sum()), n)
    print("   %-24s %+11.0f 元   加權 %+6.3f%%   對 R0h %+9.0f 元 = %+.1f pp / %.1f 年 = %+.1f pp/年%s"
          % (lab, v, v / w.sum() * 100, v - base_h, (v - base_h) / CAP * 100, span_years,
             (v - base_h) / CAP * 100 / span_years, extra))

best = max(XGRID, key=lambda X: float((df["R2" + X] * w).sum()))
print("\n=== 最佳 X = %s%% 的逐年 ===" % (float(best) * 100))
for y, g in df.groupby("year"):
    gw = g["notional"].values
    b = float((g["R0h"] * gw).sum()); v = float((g["R2" + best] * gw).sum())
    print("   %s n=%3d  差 %+9.0f 元 = 對 450 萬 %+.1f pp" % (y, len(g), v - b, (v - b) / CAP * 100))

tot = STOPS["date"].str[:4].value_counts()
rec = tot[tot.index >= "2023"].sum()
cov = (df["year"] >= "2023").sum()
print("\n=== 換算到全部真實觸價限停損 ===")
print("   2023 起可分析 %d / %d 筆（%.0f%%）。同比例放大：" % (cov, rec, cov / rec * 100))
gain = float((df["R2" + best] * w).sum()) - base_h
print("   近四年增益 %+,.0f 元 × %.2f = %+,.0f 元，除以 %.1f 年 = %+.1f pp/年"
      .replace(",", "") % (gain, rec / cov, gain * rec / cov, span_years, gain * rec / cov / CAP * 100 / span_years))
print("   對照：出貨版 2022-2026 年均 +74.5%%。加上此規則的粗估區間 %+.1f ~ %+.1f pp/年"
      % (gain / CAP * 100 / span_years, gain * rec / cov / CAP * 100 / span_years))

print("\n=== 鎖死那批若改隔天開盤回補的風險 ===")
lk = df[df["lock25"] & df["nd_open"].notna()]
for dr, sg in (("SHORT", 1.0), ("LONG", -1.0)):
    s = lk[lk["direction"] == dr]
    if not len(s):
        continue
    d = sg * (s["nd_open"] - s["slp_true"]) / s["entry"] * 100
    print("   %s n=%3d  相對停在價限：中位 %+.2f%%  p10 %+.2f%%  最差 %+.2f%%  合計 %+8.0f 元"
          % (dr, len(s), d.median(), d.quantile(0.1), d.min(), float((d / 100 * s["notional"]).sum())))
