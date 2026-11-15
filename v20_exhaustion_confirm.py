# -*- coding: utf-8 -*-
r"""Confirm: is this 量價竭盡? Can it be seen from 分K?

小哥's concept:
  量 (volume): 開盤量大 = 很多人在買/賣
  價 (price): 但價格不漲 = 買方推不動了
  竭盡 (exhaustion): 買盤用完 = 要反轉

Test: decompose the signal into its components using 1-min K-line language:
  1. 第一根分K是黑K還是紅K (first 1-min bar direction)
  2. 前幾根分K的量 (volume in first bars)
  3. 量價背離 = 大量 + 黑K (high volume + bearish candle)
  4. 連續黑K = 竭盡確認 (consecutive bearish bars = confirmed exhaustion)

This is exactly what the 富沖 app shows in its 隔日沖 tab: K棒 + 連次速量.
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
groups = short.groupby(["stock_str", "month"])

results = []
for (stock, month), grp in groups:
    if stock not in stock_dir: continue
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
        # Get first 5 one-minute bars (09:00, 09:01, 09:02, 09:03, 09:04)
        first5 = [b for b in day if "T09:0" in b["date"] and b["date"][11:16] <= "09:04"]
        if len(first5) < 2: continue

        # --- 分K 語言的特徵 ---
        # 1. 第一根K棒是紅K還是黑K
        bar1 = first5[0]
        bar1_is_black = bar1["close"] < bar1["open"]  # 黑K = 收盤 < 開盤
        bar1_body_pct = (bar1["close"] - bar1["open"]) / bar1["open"] if bar1["open"] > 0 else 0

        # 2. 前3根K棒的總量 vs 當日總量（開盤量佔比）
        vol_first3 = sum(b["volume"] for b in first5[:3])
        vol_day = sum(b["volume"] for b in day)
        vol_open_ratio = vol_first3 / vol_day if vol_day > 0 else 0

        # 3. 連續黑K數量（竭盡程度）
        consec_black = 0
        for b in first5:
            if b["close"] < b["open"]:
                consec_black += 1
            else:
                break

        # 4. 價格從開盤到 09:03 的方向
        price_dir = (first5[min(2, len(first5)-1)]["close"] - first5[0]["open"]) / first5[0]["open"]

        # 5. 量價背離 = 大量 + 價格跌
        # "大量" = 開盤量佔比 > 當日 10%（正常約 5-8%）
        high_vol = vol_open_ratio > 0.10
        price_down = price_dir < -0.005
        vol_price_divergence = high_vol and price_down

        results.append({
            "date": row["date"], "stock": stock, "p": row["p"],
            "pred_q": row["pred_q"],
            "bar1_black": bar1_is_black, "bar1_body": bar1_body_pct,
            "vol_open_ratio": vol_open_ratio, "consec_black": consec_black,
            "price_dir": price_dir, "vol_price_div": vol_price_divergence,
            "high_vol": high_vol, "price_down": price_down
        })

df = pd.DataFrame(results)
print(f"Signals with 分K data: {len(df):,}")

# === 1. 第一根分K是黑K vs 紅K ===
print("\n" + "="*70)
print("1. 第一根 1 分 K 是黑K還是紅K（開盤第一根）")
print("="*70)
for label, mask in [("黑K（收盤<開盤）", df["bar1_black"]), ("紅K（收盤>=開盤）", ~df["bar1_black"])]:
    g = df[mask]["p"]
    if len(g) < 10: continue
    print(f"  {label:<25} n={len(g):>5,} mean={g.mean()*100:+.3f}% win={(g>0).mean()*100:.1f}%")
t, p = stats.ttest_ind(df[df["bar1_black"]]["p"], df[~df["bar1_black"]]["p"], equal_var=False)
print(f"  t={t:.3f}, p={p:.2e}")

# === 2. 連續黑K（竭盡程度） ===
print("\n" + "="*70)
print("2. 連續黑K根數（越多 = 買盤越竭盡）")
print("="*70)
for n in range(0, 5):
    mask = df["consec_black"] == n
    g = df[mask]["p"]
    if len(g) < 10: continue
    print(f"  連續 {n} 根黑K: n={len(g):>5,} mean={g.mean()*100:+.3f}% win={(g>0).mean()*100:.1f}%")

# === 3. 開盤量佔比 ===
print("\n" + "="*70)
print("3. 開盤 3 分鐘量佔全日比例（正常約 5-8%）")
print("="*70)
bins_v = [0, 0.05, 0.10, 0.20, 0.40, np.inf]
labels_v = ["<5%(正常)", "5-10%", "10-20%", "20-40%", ">40%(爆量)"]
df["vol_bucket"] = pd.cut(df["vol_open_ratio"], bins=bins_v, labels=labels_v)
for label in labels_v:
    g = df[df["vol_bucket"] == label]["p"]
    if len(g) < 10: continue
    print(f"  {label:<15} n={len(g):>5,} mean={g.mean()*100:+.3f}% win={(g>0).mean()*100:.1f}%")

# === 4. 量價背離（小哥的核心概念） ===
print("\n" + "="*70)
print("4. 量價背離 = 開盤爆量(>10%) + 價格跌(>0.5%)")
print("="*70)
for label, mask in [
    ("爆量+跌（量價背離=竭盡）", df["vol_price_div"]),
    ("爆量+漲（買盤還在）", df["high_vol"] & ~df["price_down"]),
    ("正常量+跌", ~df["high_vol"] & df["price_down"]),
    ("正常量+漲", ~df["high_vol"] & ~df["price_down"]),
]:
    g = df[mask]["p"]
    if len(g) < 10: continue
    print(f"  {label:<30} n={len(g):>5,} mean={g.mean()*100:+.3f}% win={(g>0).mean()*100:.1f}%")

# === 5. 組合：黑K + 爆量（最強的竭盡訊號） ===
print("\n" + "="*70)
print("5. 最強竭盡訊號：第一根黑K + 開盤爆量")
print("="*70)
strong_exhaust = df["bar1_black"] & (df["vol_open_ratio"] > 0.10)
other = ~strong_exhaust
print(f"  黑K+爆量（竭盡確認）: n={strong_exhaust.sum():,} mean={df[strong_exhaust]['p'].mean()*100:+.3f}% win={(df[strong_exhaust]['p']>0).mean()*100:.1f}%")
print(f"  Other:                n={other.sum():,} mean={df[other]['p'].mean()*100:+.3f}% win={(df[other]['p']>0).mean()*100:.1f}%")
if strong_exhaust.sum() > 30:
    t2, p2 = stats.ttest_ind(df[strong_exhaust]["p"], df[other]["p"], equal_var=False)
    print(f"  t={t2:.3f}, p={p2:.2e}")

# === 6. 與小哥 App 欄位對照 ===
print("\n" + "="*70)
print("6. 與富沖 App「隔日沖」頁面的欄位對照")
print("="*70)
print("""
  富沖 App 欄位          |  對應的分K特徵              |  本次測試
  ─────────────────────────────────────────────────────────────────
  K棒（紅/綠）           |  第一根 1 分K 紅或黑        |  ✓ 測試 1
  連次速量              |  連續黑K + 每根的量         |  ✓ 測試 2
  隔佔比週轉率          |  開盤量佔全日比例           |  ✓ 測試 3
  成交價漲跌幅          |  09:03 價格方向             |  ✓ 測試 4
  即時走勢（圖）        |  前幾根分K 的 shape         |  ✓ 測試 5
""")

# === 7. 相關性 ===
print("="*70)
print("7. 各分K特徵與 P&L 的 Spearman 相關")
print("="*70)
for col, label in [("bar1_body", "第一根K棒實體(黑=負)"), ("consec_black", "連續黑K數"),
                   ("vol_open_ratio", "開盤量佔比"), ("price_dir", "09:03價格方向")]:
    valid = df[[col, "p"]].dropna()
    r, p = stats.spearmanr(valid[col], valid["p"])
    print(f"  {label:<25} rho={r:+.4f}, p={p:.2e}, n={len(valid):,}")

print("\nDone.")
