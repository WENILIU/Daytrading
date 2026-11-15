# -*- coding: utf-8 -*-
r"""量價竭盡 — 只用无前視指標。

所有特徵在 09:03 當下可計算：
  - 第一根K棒顏色（黑/紅）：09:01 就知道
  - 連續黑K數：09:03 就知道
  - 開盤量 vs 歷史同期開盤量：09:03 就知道（用過去同股票的中位開盤量）
  - 09:03 價格方向：09:03 就知道

不用：開盤量佔全日比例（需要等收盤才知道全日量）。
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os, json
from scipy import stats
from collections import defaultdict

DATA_PATH = r"D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線"

sig = pd.read_pickle("signals_v13.pkl")
sig["date"] = pd.to_datetime(sig["date"])
short = sig[(sig["direction"] == "SHORT") & (sig["date"] >= "2023-05-01") & (sig["date"] <= "2026-01-31")].copy()
short["stock_str"] = short["stock"].astype(str)

stock_dir = {}
for d in os.listdir(DATA_PATH):
    dp = os.path.join(DATA_PATH, d, "1")
    if not os.path.isdir(dp): continue
    files = os.listdir(dp)
    if not files: continue
    code = files[0].split("_")[0]
    if code.isdigit() and len(code) == 4:
        stock_dir[code] = dp

short["month"] = short["date"].dt.strftime("%Y-%m")

# Step 1: For each stock, compute the median opening 3-min volume across ALL days in the data
# This is the "normal" baseline. Loaded once per stock-month file.
print("Computing historical opening volume baselines...")
stock_vol_baseline = {}  # stock -> median 3-min opening volume

for stock, dp in stock_dir.items():
    all_open_vols = []
    for fname in os.listdir(dp):
        fpath = os.path.join(dp, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except: continue
        bars = data.get("data", [])
        if not bars: continue
        day_bars = defaultdict(list)
        for b in bars:
            day_bars[b["date"][:10]].append(b)
        for dt, day in day_bars.items():
            day_sorted = sorted(day, key=lambda x: x["date"])
            open_bars = [b for b in day_sorted if "T09:0" in b["date"] and b["date"][11:16] <= "09:02"]
            if len(open_bars) >= 1:
                vol = sum(b["volume"] for b in open_bars)
                if vol > 0:
                    all_open_vols.append(vol)
    if len(all_open_vols) >= 5:
        stock_vol_baseline[stock] = np.median(all_open_vols)

print(f"  Baselines computed for {len(stock_vol_baseline)} stocks")

# Step 2: Extract signal features (all available at 09:03)
print("Extracting signal features...")
groups = short.groupby(["stock_str", "month"])
results = []
processed = 0

for (stock, month), grp in groups:
    if stock not in stock_dir: continue
    baseline = stock_vol_baseline.get(stock)
    if baseline is None or baseline <= 0: continue
    fpath = os.path.join(stock_dir[stock], f"{stock}_{month}.json")
    if not os.path.exists(fpath): continue
    try:
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
    except: continue
    bars = data.get("data", [])
    if not bars: continue
    day_bars = defaultdict(list)
    for b in bars:
        day_bars[b["date"][:10]].append(b)

    for _, row in grp.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d")
        if date_str not in day_bars: continue
        day = sorted(day_bars[date_str], key=lambda x: x["date"])
        # First 3 bars: 09:00, 09:01, 09:02 (available by 09:03)
        first3 = [b for b in day if "T09:0" in b["date"] and b["date"][11:16] <= "09:02"]
        if len(first3) < 2: continue

        # --- 无前視特徵 ---
        # 1. 第一根K棒方向
        bar1 = first3[0]
        bar1_black = bar1["close"] < bar1["open"]
        bar1_body = (bar1["close"] - bar1["open"]) / bar1["open"] if bar1["open"] > 0 else 0

        # 2. 連續黑K
        consec_black = 0
        for b in first3:
            if b["close"] < b["open"]:
                consec_black += 1
            else:
                break

        # 3. 開盤量 vs 歷史同期（无前視）
        vol_3min = sum(b["volume"] for b in first3)
        vol_vs_hist = vol_3min / baseline  # >1 = 比平常大

        # 4. 價格方向到 09:02
        price_dir = (first3[-1]["close"] - first3[0]["open"]) / first3[0]["open"]

        results.append({
            "date": row["date"], "stock": stock, "p": row["p"],
            "pred_q": row["pred_q"],
            "bar1_black": bar1_black, "bar1_body": bar1_body,
            "consec_black": consec_black,
            "vol_vs_hist": vol_vs_hist,
            "price_dir": price_dir
        })
        processed += 1
        if processed % 500 == 0:
            print(f"  {processed}...")

df = pd.DataFrame(results)
print(f"\nSignals with features: {len(df):,}")

# === 1. 第一根黑K vs 紅K ===
print("\n" + "="*70)
print("1. 第一根 1 分K 顏色（09:01 即可判斷）")
print("="*70)
for label, mask in [("黑K", df["bar1_black"]), ("紅K", ~df["bar1_black"])]:
    g = df[mask]["p"]
    if len(g) < 10: continue
    print(f"  {label:<10} n={len(g):>5,} mean={g.mean()*100:+.3f}% win={(g>0).mean()*100:.1f}%")
t, p = stats.ttest_ind(df[df["bar1_black"]]["p"], df[~df["bar1_black"]]["p"], equal_var=False)
print(f"  t={t:.3f}, p={p:.2e}")

# === 2. 連續黑K ===
print("\n" + "="*70)
print("2. 連續黑K根數（09:03 即可判斷）")
print("="*70)
for n in range(0, 4):
    mask = df["consec_black"] == n
    g = df[mask]["p"]
    if len(g) < 10: continue
    print(f"  連續 {n} 根黑K: n={len(g):>5,} mean={g.mean()*100:+.3f}% win={(g>0).mean()*100:.1f}%")

# === 3. 開盤量 vs 歷史同期（无前視） ===
print("\n" + "="*70)
print("3. 開盤量 vs 歷史同期中位量（09:03 即可計算，无前視）")
print("="*70)
bins_v = [0, 0.5, 1.0, 2.0, 4.0, np.inf]
labels_v = ["<0.5x(縮量)", "0.5-1x", "1-2x", "2-4x", ">4x(爆量)"]
df["vol_bucket"] = pd.cut(df["vol_vs_hist"], bins=bins_v, labels=labels_v)
for label in labels_v:
    g = df[df["vol_bucket"] == label]["p"]
    if len(g) < 10: continue
    print(f"  {label:<15} n={len(g):>5,} mean={g.mean()*100:+.3f}% win={(g>0).mean()*100:.1f}%")

# === 4. 量價背離（无前視版） ===
print("\n" + "="*70)
print("4. 量價背離 = 爆量(>2x歷史) + 價格跌（全部无前視）")
print("="*70)
high_vol = df["vol_vs_hist"] > 2.0
price_down = df["price_dir"] < -0.005
for label, mask in [
    ("爆量+跌（量價背離=竭盡）", high_vol & price_down),
    ("爆量+漲（買盤還在）", high_vol & ~price_down),
    ("正常量+跌", ~high_vol & price_down),
    ("正常量+漲", ~high_vol & ~price_down),
]:
    g = df[mask]["p"]
    if len(g) < 10: continue
    print(f"  {label:<30} n={len(g):>5,} mean={g.mean()*100:+.3f}% win={(g>0).mean()*100:.1f}%")

# === 5. 最強訊號：黑K + 爆量 ===
print("\n" + "="*70)
print("5. 竭盡確認：第一根黑K + 開盤爆量(>2x歷史)")
print("="*70)
exhaust = df["bar1_black"] & (df["vol_vs_hist"] > 2.0)
other = ~exhaust
print(f"  黑K+爆量（竭盡）: n={exhaust.sum():,} mean={df[exhaust]['p'].mean()*100:+.3f}% win={(df[exhaust]['p']>0).mean()*100:.1f}%")
print(f"  Other:           n={other.sum():,} mean={df[other]['p'].mean()*100:+.3f}% win={(df[other]['p']>0).mean()*100:.1f}%")
if exhaust.sum() > 30:
    t2, p2 = stats.ttest_ind(df[exhaust]["p"], df[other]["p"], equal_var=False)
    print(f"  t={t2:.3f}, p={p2:.2e}")

# === 6. 策略層：確認後才進場（无前視版） ===
print("\n" + "="*70)
print("6. 策略層：09:03 確認黑K+跌才進場（无前視）")
print("="*70)
# Adjusted P&L for 09:03 entry
df["p_0903"] = df["p"] + df["price_dir"]

# A: current (09:00 all)
a = df["p"]
print(f"  A: 09:00 全部進場:     n={len(a):,} mean={a.mean()*100:+.3f}% win={(a>0).mean()*100:.1f}%")

# B: 09:03 all (no filter)
b = df["p_0903"]
print(f"  B: 09:03 全部進場:     n={len(b):,} mean={b.mean()*100:+.3f}% win={(b>0).mean()*100:.1f}%")

# C: 09:03 + 黑K確認
c_black = df[df["bar1_black"]]["p_0903"]
print(f"  C: 09:03 + 第一根黑K:  n={len(c_black):,} mean={c_black.mean()*100:+.3f}% win={(c_black>0).mean()*100:.1f}%")

# D: 09:03 + 黑K + 爆量
c_strong = df[df["bar1_black"] & (df["vol_vs_hist"] > 2.0)]["p_0903"]
if len(c_strong) > 10:
    print(f"  D: 09:03 + 黑K + 爆量: n={len(c_strong):,} mean={c_strong.mean()*100:+.3f}% win={(c_strong>0).mean()*100:.1f}%")

# E: 09:03 + 價格跌>0.5%
c_price = df[df["price_dir"] < -0.005]["p_0903"]
print(f"  E: 09:03 + 跌>0.5%:    n={len(c_price):,} mean={c_price.mean()*100:+.3f}% win={(c_price>0).mean()*100:.1f}%")

# === 7. 相關性 ===
print("\n" + "="*70)
print("7. Spearman 相關（全部无前視指標）")
print("="*70)
for col, label in [("bar1_body", "第一根K棒實體"), ("consec_black", "連續黑K數"),
                   ("vol_vs_hist", "開盤量/歷史"), ("price_dir", "09:03價格方向")]:
    valid = df[[col, "p"]].dropna()
    r, p = stats.spearmanr(valid[col], valid["p"])
    print(f"  {label:<20} rho={r:+.4f}, p={p:.2e}, n={len(valid):,}")

print("\nDone.")
