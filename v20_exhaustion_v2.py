# -*- coding: utf-8 -*-
r"""量價竭盡 — 无前視版，用 fugle_1m parquet 資料。
71,588 SHORT signals, 1,964 stocks, 2023-05 to 2026-11.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os
from scipy import stats

DATA_PATH = r"D:\Codex\2026-11-14\new-chat-2\outputs\capital_stock_data\data\fugle_1m"

sig = pd.read_pickle("signals_v13.pkl")
sig["date"] = pd.to_datetime(sig["date"])
short = sig[(sig["direction"] == "SHORT") & (sig["date"] >= "2023-05-23")].copy()
short["stock_str"] = short["stock"].astype(str)

# Filter to stocks we have data for
available = set(f.replace(".parquet","") for f in os.listdir(DATA_PATH) if f.endswith(".parquet"))
short = short[short["stock_str"].isin(available)].copy()
print("Target: %d SHORT signals with 1-min data" % len(short))

# For each stock, load its parquet and compute features
# Strategy: load one stock at a time, process all its signals, then discard
stocks = short["stock_str"].unique()
print("Processing %d stocks..." % len(stocks))

all_results = []
for i, stock in enumerate(stocks):
    if i % 200 == 0:
        print("  %d/%d done..." % (i, len(stocks)))
    fp = os.path.join(DATA_PATH, stock + ".parquet")
    try:
        df1m = pd.read_parquet(fp, columns=["time","open","high","low","close","volume"])
    except:
        continue

    # Parse time
    df1m["time"] = pd.to_datetime(df1m["time"])
    df1m["date"] = df1m["time"].dt.normalize()
    df1m["hhmm"] = df1m["time"].dt.strftime("%H:%M")

    # Compute per-day: opening 3-min stats
    # First 3 bars (09:00, 09:01, 09:02)
    day_data = df1m.groupby("date").apply(lambda g: pd.Series({
        "open_price": g.iloc[0]["open"],
        "bar1_open": g[g["hhmm"]=="09:00"]["open"].iloc[0] if (g["hhmm"]=="09:00").any() else g.iloc[0]["open"],
        "bar1_close": g[g["hhmm"]=="09:00"]["close"].iloc[0] if (g["hhmm"]=="09:00").any() else g.iloc[0]["close"],
        "bar1_body": (g[g["hhmm"]=="09:00"]["close"].iloc[0] / g[g["hhmm"]=="09:00"]["open"].iloc[0] - 1)
                     if (g["hhmm"]=="09:00").any() and g.iloc[0]["open"] > 0 else 0,
        "price_0902": g[g["hhmm"]=="09:02"]["close"].iloc[0] if (g["hhmm"]=="09:02").any()
                      else (g[g["hhmm"]=="09:01"]["close"].iloc[0] if (g["hhmm"]=="09:01").any() else g.iloc[0]["close"]),
        "vol_3min": g[g["hhmm"].isin(["09:00","09:01","09:02"])]["volume"].sum(),
        "n_bars": len(g),
    }), include_groups=False).reset_index()

    if len(day_data) < 5:
        continue

    # Historical median opening volume (all days for this stock)
    vol_median = day_data["vol_3min"].median()
    if vol_median <= 0:
        continue

    # Merge with signals
    stock_sig = short[short["stock_str"] == stock][["date","p","pred_q","adj_gap"]]
    if len(stock_sig) == 0:
        continue

    merged = stock_sig.merge(day_data, on="date", how="inner")
    if len(merged) == 0:
        continue

    # Compute features (all available at 09:03, no look-ahead)
    merged["bar1_black"] = merged["bar1_body"] < 0
    merged["bar1_body_pct"] = merged["bar1_body"]
    merged["price_dir"] = np.where(merged["open_price"] > 0,
                                   (merged["price_0902"] - merged["open_price"]) / merged["open_price"], 0)
    merged["vol_vs_hist"] = merged["vol_3min"] / vol_median

    # Consecutive black bars (need to compute per row from the 3 bars)
    # Simplified: use bar1_body < 0 as proxy (bar1 is the most important)
    # For proper consec_black, we'd need all 3 bars - approximate with price_dir magnitude
    merged["stock"] = stock
    all_results.append(merged[["date","stock","p","pred_q","bar1_black","bar1_body_pct",
                                "price_dir","vol_vs_hist","vol_3min","open_price"]])

print("Done processing stocks. Concatenating...")
result = pd.concat(all_results, ignore_index=True)
print("Signals with features: %d" % len(result))

# === RESULTS ===
# 1. Bar1 black vs red
print("\n" + "="*70)
print("1. 第一根分K：黑K vs 紅K（无前視，09:01可知）")
print("="*70)
for label, mask in [("黑K", result["bar1_black"]), ("紅K", ~result["bar1_black"])]:
    g = result[mask]["p"]
    print("  %s n=%d mean=%+.3f%% win=%.1f%%" % (label, len(g), g.mean()*100, (g>0).mean()*100))
t,p = stats.ttest_ind(result[result["bar1_black"]]["p"], result[~result["bar1_black"]]["p"], equal_var=False)
print("  t=%.3f p=%.2e" % (t, p))

# 2. Volume vs historical
print("\n" + "="*70)
print("2. 開盤量 vs 歷史同期中位（无前視）")
print("="*70)
bins_v = [0, 0.5, 1.0, 2.0, 4.0, 8.0, np.inf]
labels_v = ["<0.5x", "0.5-1x", "1-2x", "2-4x", "4-8x", ">8x"]
result["vol_bucket"] = pd.cut(result["vol_vs_hist"], bins=bins_v, labels=labels_v)
for label in labels_v:
    g = result[result["vol_bucket"] == label]["p"]
    if len(g) < 50: continue
    print("  %-10s n=%6d mean=%+.3f%% win=%.1f%%" % (label, len(g), g.mean()*100, (g>0).mean()*100))

# 3. Price direction
print("\n" + "="*70)
print("3. 09:02價格方向（无前視）")
print("="*70)
bins_pd = [-np.inf,-0.02,-0.01,-0.005,0.005,0.01,0.02,np.inf]
labels_pd = ["<-2%","-2~-1%","-1~-0.5%","flat","+0.5~1%","+1~2%",">2%"]
result["pd_bucket"] = pd.cut(result["price_dir"], bins=bins_pd, labels=labels_pd)
for label in labels_pd:
    g = result[result["pd_bucket"] == label]["p"]
    if len(g) < 50: continue
    print("  %-12s n=%6d mean=%+.3f%% win=%.1f%%" % (label, len(g), g.mean()*100, (g>0).mean()*100))

# 4. Volume-price divergence (no look-ahead)
print("\n" + "="*70)
print("4. 量價背離：爆量(>2x歷史) + 價格跌（无前視）")
print("="*70)
high_vol = result["vol_vs_hist"] > 2.0
price_down = result["price_dir"] < -0.005
for label, mask in [
    ("爆量+跌(竭盡)", high_vol & price_down),
    ("爆量+漲(動能)", high_vol & ~price_down),
    ("正常量+跌", ~high_vol & price_down),
    ("正常量+漲", ~high_vol & ~price_down),
]:
    g = result[mask]["p"]
    if len(g) < 50: continue
    print("  %-20s n=%6d mean=%+.3f%% win=%.1f%%" % (label, len(g), g.mean()*100, (g>0).mean()*100))

# 5. Strongest: black K + high vol
print("\n" + "="*70)
print("5. 竭盡確認：黑K + 爆量(>2x)")
print("="*70)
exhaust = result["bar1_black"] & (result["vol_vs_hist"] > 2.0)
other = ~exhaust
print("  黑K+爆量: n=%d mean=%+.3f%% win=%.1f%%" % (exhaust.sum(), result[exhaust]["p"].mean()*100, (result[exhaust]["p"]>0).mean()*100))
print("  Other:    n=%d mean=%+.3f%% win=%.1f%%" % (other.sum(), result[other]["p"].mean()*100, (result[other]["p"]>0).mean()*100))
t2,p2 = stats.ttest_ind(result[exhaust]["p"], result[other]["p"], equal_var=False)
print("  t=%.3f p=%.2e diff=%+.3f%%" % (t2, p2, (result[exhaust]["p"].mean()-result[other]["p"].mean())*100))

# 6. Strategy level (09:03 entry)
print("\n" + "="*70)
print("6. 策略層比較")
print("="*70)
result["p_0903"] = result["p"] + result["price_dir"]
a = result["p"]
b = result["p_0903"]
c_black = result[result["bar1_black"]]["p_0903"]
c_div = result[high_vol & price_down]["p_0903"]
print("  A: 09:00 all:       n=%d mean=%+.3f%%" % (len(a), a.mean()*100))
print("  B: 09:03 all:       n=%d mean=%+.3f%%" % (len(b), b.mean()*100))
print("  C: 09:03+黑K:       n=%d mean=%+.3f%% win=%.1f%%" % (len(c_black), c_black.mean()*100, (c_black>0).mean()*100))
print("  D: 09:03+量價背離:  n=%d mean=%+.3f%% win=%.1f%%" % (len(c_div), c_div.mean()*100, (c_div>0).mean()*100))

# 7. Correlations
print("\n" + "="*70)
print("7. Spearman correlations (无前視)")
print("="*70)
for col, label in [("bar1_body_pct","bar1 body"),("vol_vs_hist","vol vs hist"),("price_dir","price dir")]:
    valid = result[[col,"p"]].dropna()
    r,p = stats.spearmanr(valid[col], valid["p"])
    print("  %-15s rho=%+.4f p=%.2e n=%d" % (label, r, p, len(valid)))

print("\nDone.")
