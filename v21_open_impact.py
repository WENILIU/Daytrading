# -*- coding: utf-8 -*-
import os, json, glob, sys, io, datetime, warnings; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
# (A) 開盤真實成交滑價探针(到達價模型)。**決策在 09:01:00(第一分K收盤)才下單**，
#   所以到達價=09:01 當時的買賣 midpoint，吃單窗口從 09:01 開始，分母=09:01 分鐘量。
#   真實逐筆: 股票成交明細_full/<code>/<code>_<date>.json。SHORT=賣方收到較低=成本，加半價差一次穿越。
ROOT = r"D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票成交明細_full"
LADDER = [0.05, 0.10, 0.20, 0.30, 0.50, 1.00]
DEC = 9 * 60 + 1   # 09:01 決策/成交窗口起點
def ts_of(r): return datetime.datetime.fromtimestamp(r["time"] / 1e6)
def after_dec(rows): return [r for r in rows if (ts_of(r).hour * 60 + ts_of(r).minute) >= DEC]
def minute_vol_541(rows):
    s = 0.0
    for r in rows:
        t = ts_of(r)
        if t.hour == 9 and t.minute == 1: s += r["size"]
    return s
def arrival_ref(rows):
    for r in rows:
        if (ts_of(r).hour * 60 + ts_of(r).minute) < DEC: continue
        if r.get("bid", 0) > 0 and r.get("ask", 0) > 0:
            b, a = r["bid"], r["ask"]; return (b + a) / 2.0, (a - b) / 2.0
    return rows[0]["price"], 0.0
def walk(rows, target_size):
    acc = num = 0.0; t0 = tf = None
    for r in rows:
        t = ts_of(r)
        if t0 is None: t0 = t
        if acc >= target_size:
            tf = (t - t0).total_seconds(); break
        num += r["price"] * r["size"]; acc += r["size"]
    else:
        if rows: tf = (ts_of(rows[-1]) - t0).total_seconds()
    return (num / acc if acc else np.nan), tf
def load(fp):
    d = json.load(open(fp, encoding="utf-8"))
    return sorted(d["data"], key=lambda r: r["serial"]), d["symbol"], d.get("date", "")

mode = sys.argv[1] if len(sys.argv) > 1 else "ladder"
files = glob.glob(os.path.join(ROOT, "*", "*.json"))
print(f"=== (A) 開盤滑價探针 [{mode}] (到達價=09:01, 窗口從決策點起) ===")
print(f"逐筆檔案 {len(files)} 個。目前是 generic 取樣/前向累积, n 小需留意。\n")
rows_out = []
for fp in files:
    try: rows_all, code, day = load(fp)
    except Exception: continue
    rows = after_dec(rows_all)
    fvol = minute_vol_541(rows_all)
    if not (fvol > 0 and len(rows) >= 2): continue
    ref, half = arrival_ref(rows_all)
    if mode == "real":
        if not os.path.exists("fill_probe/participation.csv"):
            print("缺 participation.csv(先跑 v21_liqcap_build.py)"); sys.exit(0)
        pr = pd.read_csv("fill_probe/participation.csv", dtype={"s": str}); pr["s"] = pr["s"].astype(str).str.zfill(4)
        for _, h in pr[(pr["s"] == code) & (pr["date"].astype(str) == str(day))].iterrows():
            fill, tf = walk(rows, h["my張"] * 1000.0)
            if not np.isfinite(fill): continue
            drift = (ref - fill) / ref * 100.0; cost = max(drift, 0.0) + half / ref * 100.0
            rows_out.append(dict(code=code, date=day, part_pct=h["part"], cost_pct=cost, drift_pct=drift, tfill_s=tf))
        continue
    for p in LADDER:
        fill, tf = walk(rows, p * fvol)
        if not np.isfinite(fill): continue
        drift = (ref - fill) / ref * 100.0; cost = max(drift, 0.0) + half / ref * 100.0
        rows_out.append(dict(code=code, p=p * 100, fvol=fvol, ref=ref, fill=fill, drift_pct=drift, cost_pct=cost, tfill_s=tf))
if not len(rows_out):
    print("無可配對真實交易逐筆(前向未累積)。用 `python v21_open_impact.py ladder` 看方法示範。"); sys.exit(0)
df = pd.DataFrame(rows_out)
if mode == "real":
    df.to_csv("fill_probe/open_impact_real.csv", index=False, encoding="utf-8-sig")
    print(f"{'實際參與率(09:01)區間':>18} | {'筆數':>5} | {'平均真實滑價%':>13} | {'中位%':>8} | {'平均成交秒':>9}")
    print("-"*72)
    for lo, hi in [(0,5),(5,10),(10,30),(30,100),(100,1e12)]:
        s = df[(df["part_pct"] >= lo) & (df["part_pct"] < hi)]
        if len(s): print(f"{f'{lo}-{hi if hi<1e9 else chr(43)}%':>18} | {len(s):>5} | {s['cost_pct'].mean():>12.3f}% | {s['cost_pct'].median():>7.3f}% | {s['tfill_s'].mean():>8.1f}")
    print(f"\n寫入 fill_probe/open_impact_real.csv  n={len(df)}")
else:
    df.to_csv("fill_probe/open_impact_demo.csv", index=False, encoding="utf-8-sig")
    print(f"{'參與率p(09:01後%)':>16} | {'平均到達價滑價%(賣方成本)':>24} | {'平均成交時間(s)':>16} | {'中位滑價%':>10}")
    print("-"*80)
    for p in LADDER:
        s = df[abs(df["p"] - p * 100) < 1e-6]
        if len(s): print(f"{p*100:>15.0f}% | {s['cost_pct'].mean():>23.3f}% | {s['tfill_s'].mean():>15.1f} | {s['cost_pct'].median():>9.3f}%")
    print(f"\n方法示範 n={df['code'].nunique()} 標的(單日, 窗口 09:01 起)。寫入 fill_probe/open_impact_demo.csv")
