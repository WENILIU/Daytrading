import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]: os.environ[k]="1"
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

# (B) 真實開盤第一分鐘量能 cap 敏感度：
#   若單張數 > 該股真實 09:01 前分鐘成交量的 cap%，只能成交 cap/part 的部位，
#   該筆 PnL 線性縮到 sc=min(1, cap/part)。用逐筆(固定450萬基準)重建每日淨額→年均/MDD。
P450 = 4_500_000.0
df = pd.read_csv("fill_probe/participation.csv")
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").reset_index(drop=True)
years = (df["date"].max() - df["date"].min()).days / 365.25

def stats(scale):
    y = df["yuan"].values * scale
    d = pd.Series(y).groupby(df["date"]).sum().sort_index()
    cum = d.cumsum().values
    mdd = (cum - np.maximum.accumulate(cum)).min() / P450 * 100.0   # 固定基準部位回撤
    total = d.sum() / P450 * 100.0                                   # 固定基準累計(非複利)
    ann = total / years
    win = (d > 0).mean() * 100.0
    return ann, mdd, total, win

base_scale = np.ones(len(df))
ann0, mdd0, tot0, win0 = stats(base_scale)
print("=== (B) 真實開盤量能 cap 敏感度 (口徑: 逐筆固定450萬基準, 非複利) ===")
print(f"樣本 {len(df)} 筆 | 區間 {df['date'].min().date()}~{df['date'].max().date()} ({years:.2f} 年)")
print(f"基準(無上限): 固定基準年均 {ann0:+.1f}%  部位MDD {mdd0:+.2f}%  獲利日 {win0:.1f}%")
print("  (此為固定基準非複利口徑, 與 README 複利 headline 不同尺度; 重點看相對保留率)\n")
print(f"{'cap(真實第一分鐘量能%)':>22} | {'需縮筆數':>8} | {'保留PnL%':>8} | {'固定年均':>8} | {'MDD':>7} | {'Δ年均':>7}")
print("-"*82)
for cap in [1e9, 30, 20, 15, 10, 7, 5, 3, 2]:
    sc = np.clip(cap / df["part"].values, 0.0, 1.0)
    need = int((sc < 0.999).sum())
    ann, mdd, tot, win = stats(sc)
    ret = tot / tot0 * 100.0
    lbl = "無上限" if cap > 1e8 else f"{cap:.0f}%"
    print(f"{lbl:>22} | {need:>8} | {ret:>7.1f}% | {ann:>+7.1f}% | {mdd:>+6.2f}% | {ann-ann0:>+6.1f}")
