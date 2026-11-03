import warnings; warnings.filterwarnings("ignore")
import pickle, numpy as np, pandas as pd
import v13_target as T

df = pickle.load(open("_min1_lock.pkl", "rb"))
df["date"] = pd.to_datetime(df["date"].astype(str))
d = df.dropna(subset=["nd_open", "close_1325"]).copy()
sh = d[d["direction"] == "SHORT"].copy()
sh["pinned"] = sh["close_1325"] >= sh["lim"] - 1e-9
sh["overnight"] = (sh["close_1325"] - sh["nd_open"]) / sh["entry"] * 100   # + = next open cheaper
pin = sh[sh["pinned"]]
print("=== 鎖死放空：從收盤漲停到隔天開盤 ===")
print("n =", len(pin))
s = pin["overnight"]
print("平均 %+0.3f%%   中位 %+0.3f%%" % (s.mean(), s.median()))
print("隔天開盤比較便宜(還本)的比例: %.1f%%" % (s > 0).mean() * 100)
for q in (5, 10, 25, 50, 75, 90, 95):
    print("   p%-2d %+0.2f%%" % (q, s.quantile(q / 100)))
print("由進價算的總虧損: 收盤漲停 p50 %+0.2f%%   隔天開盤 p50 %+0.2f%%"
      % (((pin["lim"] - pin["entry"]) / pin["entry"] * 100).median(),
         (-(pin["nd_open"] - pin["entry"]) / pin["entry"] * 100).median()))
print()
print("=== 基礎機率：全部放空訊號依 zt_close_60 分組的鎖死率 ===")
D = T.D
sh2 = D[D["direction"] == "SHORT"].copy()
sh2["zc"] = pd.to_numeric(sh2.get("zt_close_60"), errors="coerce").fillna(0)
sh2["pin"] = sh2["day_close"] >= sh2["lu"] - 1e-9
bins = [-1, 0, 1, 3, 6, 12, 999]
lbl = ["0", "1", "2-3", "4-6", "7-12", "13+"]
sh2["b"] = pd.cut(sh2["zc"], bins, labels=lbl)
g = sh2.groupby("b", observed=False).agg(n=("pin", "size"), pin=("pin", "sum"))
g["share_of_signals"] = g["n"] / g["n"].sum() * 100
g["pin_rate"] = g["pin"] / g["n"] * 100
g["share_of_locks"] = g["pin"] / g["pin"].sum() * 100
print(g.to_string(float_format=lambda x: "%8.2f" % x))
print("\n全部放空訊號 %d，鎖死 %d，總鎖死率 %.2f%%" % (len(sh2), int(g["pin"].sum()), g["pin"].sum() / len(sh2) * 100))
