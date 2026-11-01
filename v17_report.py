# -*- coding: utf-8 -*-
r"""Read _min1_lock.pkl and compare the three exit rules on the same trades.

Everything here is first-order: it re-prices the trades that already stopped out
on a price limit and nothing else. It ignores the capital that would have been
freed earlier and could have been redeployed, so it understates a rule that wins
and overstates nothing. Notional-weighted TWD is divided by the 4.5M account
limit so the numbers are directly comparable to the yearly profit table.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np

CAP = 4_500_000.0
df = pd.read_pickle("_min1_lock.pkl")
XS = ["0.005", "0.010", "0.015", "0.020", "0.030"]
df["year"] = [x[:4] for x in df["date"]]
n = len(df)
print("樣本：%d 筆觸板停損，%d 檔股票，%s ~ %s"
      % (n, df["code"].nunique(), df["date"].min(), df["date"].max()))
print("方向：SHORT %d / LONG %d" % ((df["direction"] == "SHORT").sum(),
                                   (df["direction"] == "LONG").sum()))

print("\n=== 1. 覆蓋率（各年能分析的 / 全部觸板停損）===")
allst = pd.read_pickle("_min1_all_stops.pkl")
tot = pd.Series([str(x[0])[:4] for x in allst]).value_counts()
got = df["year"].value_counts()
for y in sorted(tot.index):
    print("   %s  %5d / %5d  %5.1f%%" % (y, got.get(y, 0), tot[y], got.get(y, 0) / tot[y] * 100))

print("\n=== 2. 觸板之後：鎖到收盤 vs 解開 ===")
print("   鎖到收盤  %5d  %5.1f%%" % (df["locked"].sum(), df["locked"].mean() * 100))
print("   曾解開    %5d  %5.1f%%" % ((~df["locked"]).sum(), (1 - df["locked"].mean()) * 100))
print("\n   逐年：")
for y, g in df.groupby("year"):
    if len(g) < 20:
        continue
    print("   %s  n=%4d  鎖死 %5.1f%%   現行停損平均 %+6.2f%%   結在收盤 %+6.2f%%"
          % (y, len(g), g["locked"].mean() * 100,
             (g["r0"] * g["notional"]).sum() / g["notional"].sum() * 100,
             (g["r1"] * g["notional"]).sum() / g["notional"].sum() * 100), flush=True)

print("\n=== 3. 觸板時間與解開速度 ===")
print("   觸板時間分布（每 30 分鐘）：")
buck = pd.cut(df["touch_time"].str[:2].astype(int) * 60 + df["touch_time"].str[3:5].astype(int),
              bins=list(range(540, 841, 30)), right=False)
for k, v in buck.value_counts().sort_index().items():
    print("      %-14s %5d" % (str(k), v))
d = df[df["hit_0.010"] != ""].copy()
if len(d):
    mins = (d["hit_0.010"].str[:2].astype(int) * 60 + d["hit_0.010"].str[3:5].astype(int)
            - d["touch_time"].str[:2].astype(int) * 60 - d["touch_time"].str[3:5].astype(int))
    print("   觸板後跌回 1%% 所需分鐘：中位 %.0f  p90 %.0f  最大 %.0f"
          % (mins.median(), mins.quantile(0.9), mins.max()))

print("\n=== 4. 三條規則在同一批交易上的結果 ===")
print("   （只計這批交易本身的損益變化，未計資金提前釋放再投資）")
w = df["notional"].values
base = float((df["r0"] * w).sum())
print("   R0 現行（觸板即停損）        合計 %+12.0f 元   平均每筆 %+6.3f%%"
      % (base, (df["r0"] * w).sum() / w.sum() * 100))
r1 = float((df["r1"] * w).sum())
print("   R1 結在收盤（上界，不可執行）合計 %+12.0f 元   平均每筆 %+6.3f%%   差異 %+11.0f 元 = %+.1f pp/期間"
      % (r1, (df["r1"] * w).sum() / w.sum() * 100, r1 - base, (r1 - base) / CAP * 100))
for X in XS:
    c = "r2_" + X
    v = float((df[c] * w).sum())
    filled = (df["hit_" + X] != "").sum()
    print("   R2 掛在漲跌停下方 %.1f%%    合計 %+12.0f 元   成交 %4d/%d 筆   差異 %+11.0f 元 = %+.1f pp/期間"
          % (float(X) * 100, v, filled, n, v - base, (v - base) / CAP * 100), flush=True)

print("\n=== 5. 逐年 R2(1%%) 對 R0 的金額差 ===")
for y, g in df.groupby("year"):
    if len(g) < 20:
        continue
    gw = g["notional"].values
    d0 = float((g["r2_0.010"] * gw).sum() - (g["r0"] * gw).sum())
    print("   %s  n=%4d  差異 %+10.0f 元  = 對 450 萬 %+.1f pp" % (y, len(g), d0, d0 / CAP * 100))

print("\n=== 6. 鎖死那批的隔天實際結果（無法盤中回補的真實成本）===")
lk = df[df["locked"] & df["nd_open"].notna()].copy()
if len(lk):
    if (lk["direction"] == "SHORT").any():
        s = lk[lk["direction"] == "SHORT"]
        go = (s["nd_open"] - s["lim"]) / s["lim"] * 100
        gc = (s["nd_close"] - s["lim"]) / s["lim"] * 100
        print("   SHORT 鎖漲停 n=%d：隔天開盤相對漲停價 中位 %+.2f%%  p10 %+.2f%%  p90 %+.2f%%"
              % (len(s), go.median(), go.quantile(0.1), go.quantile(0.9)))
        print("                            隔天收盤相對漲停價 中位 %+.2f%%  p10 %+.2f%%  p90 %+.2f%%"
              % (gc.median(), gc.quantile(0.1), gc.quantile(0.9)))
    if (lk["direction"] == "LONG").any():
        s = lk[lk["direction"] == "LONG"]
        go = (s["lim"] - s["nd_open"]) / s["lim"] * 100
        gc = (s["lim"] - s["nd_close"]) / s["lim"] * 100
        print("   LONG 鎖跌停 n=%d：隔天開盤相對跌停價 中位 %+.2f%%  p10 %+.2f%%  p90 %+.2f%%"
              % (len(s), go.median(), go.quantile(0.1), go.quantile(0.9)))
        print("                           隔天收盤相對跌停價 中位 %+.2f%%  p10 %+.2f%%  p90 %+.2f%%"
              % (gc.median(), gc.quantile(0.1), gc.quantile(0.9)))
    print("   （正值 = 對我們有利，負值 = 比停在價限上更虧）")
else:
    print("   無可比的隔天資料")
