# -*- coding: utf-8 -*-
import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]: os.environ[k]="1"
import sys, io, warnings; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
# 逐筆真實開盤量能參與率。**決策在 09:00 分K收盤(=09:01:00)才算出 price_dir 並下單，
#   成交發生在 09:01 那一分鐘** -> 可成交量的正確分母 = 09:01 分鐘(第二根)的量, 不是開盤第一分鐘。
#   本腳本一次算 540(第一分鐘) 與 541(第二分鐘) 兩個分母, 供對照。主表用 541。
TRADES = sys.argv[1] if len(sys.argv) > 1 else r"v21_trades_2023-05-23_2026-12-31.csv"
ONE = r"D:\Codex\2026-11-14\new-chat-2\outputs\capital_stock_data\data\fugle_1m"
ONEF = {f[:-8]: os.path.join(ONE, f) for f in os.listdir(ONE)} if os.path.isdir(ONE) else {}
_cache = {}
def mins_vol(code, day):
    """回傳 (v540張, v541張)：09:00 與 09:01 各自真實分鐘成交量(張)。"""
    k = (code, day)
    if k in _cache: return _cache[k]
    p = ONEF.get(code)
    if not p:
        _cache[k] = (np.nan, np.nan); return _cache[k]
    try:
        m = pd.read_parquet(p, columns=["time", "volume"])
    except Exception:
        _cache[k] = (np.nan, np.nan); return _cache[k]
    t = pd.to_datetime(m["time"]); gm = (t.dt.hour * 60 + t.dt.minute).values; d = t.dt.normalize()
    day_ts = pd.Timestamp(day)
    same = (d == day_ts).values
    v540 = float(m["volume"].values[(same & (gm == 540))].sum())
    v541 = float(m["volume"].values[(same & (gm == 541))].sum())
    _cache[k] = (v540, v541)
    return v540, v541

t = pd.read_csv(TRADES, dtype={"股票": str}); t.columns = [c.strip() for c in t.columns]
rows = []
for _, r in t.iterrows():
    code = str(r["股票"]).zfill(4); day = str(r["日期"]); my = float(r["張數"])
    v540, v541 = mins_vol(code, day)
    if not (np.isfinite(v541) and v541 > 0):   # 第二分鐘要有量才算得出真實可成交性
        continue
    rows.append(dict(date=day, s=code, my張=my, fvol張=v541, part=my / v541 * 100.0,
                     part_540=(my / v540 * 100.0 if np.isfinite(v540) and v540 > 0 else np.nan),
                     net=r["淨pct"], 名義=r["名義額"], yuan=r["淨額元"]))
df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
os.makedirs("fill_probe", exist_ok=True)
df.to_csv("fill_probe/participation.csv", index=False, encoding="utf-8-sig")
df.to_csv("fill_probe/participation_540vs541.csv", index=False, encoding="utf-8-sig")
print(f"WROTE participation.csv (分母=09:01第二分鐘量) {len(df)} 筆")
def dist(col, label):
    p = df[col].dropna()
    print(f"\n[{label}] 參與率分布: 中位 {p.median():.1f}%  p90 {p.quantile(.9):.0f}%  p99 {p.quantile(.99):.0f}%  max {p.max():.0f}%")
    print(f"    >10% {int((p>10).sum())} ({(p>10).mean()*100:.0f}%)   >30% {int((p>30).sum())} ({(p>30).mean()*100:.0f}%)")
    for th in [10, 20, 30]:
        s = df[df[col] > th]
        print(f"    >{th}% 族群: 佔獲利 {s['yuan'][s.yuan>0].sum()/df['yuan'][df.yuan>0].sum()*100:.1f}%  平均該分鐘量能 {s['fvol張'].median():.0f} 張")
print(f"對照平均量: 09:00第一分鐘 {df['my張'].div(df['my張']).mul(1).median():.0f}(略)  第二分鐘中位 {df['fvol張'].median():.0f} 張")
dist("part_540", "舊口徑: 對第一分鐘(09:00)量能")
dist("part",     "修正口徑: 對第二分鐘(09:01)量能 <- 你實際下單窗口")
