# -*- coding: utf-8 -*-
r"""量價竭盡 v3 — 向量化版本，无前視。
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os
from scipy import stats

DATA_PATH = r"D:\Codex\2026-11-14\new-chat-2\outputs\capital_stock_data\data\fugle_1m"

sig = pd.read_pickle("signals_v13.pkl")
sig["date"] = pd.to_datetime(sig["date"])
short = sig[(sig["direction"] == "SHORT") & (sig["date"] >= "2023-05-23")].copy()
short["stock_str"] = short["stock"].astype(str)

available = set(f.replace(".parquet","") for f in os.listdir(DATA_PATH) if f.endswith(".parquet"))
short = short[short["stock_str"].isin(available)].copy()
print("Target: %d SHORT signals, %d stocks" % (len(short), short["stock_str"].nunique()))

# Vectorized: for each stock, load parquet once, extract opening features
stocks = short["stock_str"].unique()
all_features = []

for i, stock in enumerate(stocks):
    if i % 300 == 0:
        print("  %d/%d..." % (i, len(stocks)))
    fp = os.path.join(DATA_PATH, stock + ".parquet")
    try:
        d = pd.read_parquet(fp)
    except:
        continue
    d["time"] = pd.to_datetime(d["time"])
    d["date"] = d["time"].dt.date
    d["hhmm"] = d["time"].dt.strftime("%H:%M")

    # Filter to opening minutes only (09:00-09:02)
    open_bars = d[d["hhmm"].isin(["09:00","09:01","09:02"])].copy()
    if len(open_bars) == 0:
        continue

    # Pivot: for each date, get bar1 open/close and sum volume
    # Sort by time to ensure order
    open_bars = open_bars.sort_values("time")

    # Get first bar per date (bar1 = 09:00)
    bar1 = open_bars.groupby("date").first().rename(columns={
        "open": "bar1_open", "close": "bar1_close", "high": "bar1_high", "low": "bar1_low", "volume": "bar1_vol"
    })
    # Get last bar per date (09:02 close)
    bar_last = open_bars.groupby("date").last().rename(columns={"close": "close_0902", "volume": "vol_last"})
    # Volume sum per date
    vol_sum = open_bars.groupby("date")["volume"].sum().rename("vol_3min")

    # Combine
    feat = bar1[["bar1_open","bar1_close","bar1_vol"]].join(bar_last[["close_0902"]]).join(vol_sum)
    feat = feat.reset_index()
    feat["date"] = pd.to_datetime(feat["date"])

    # Compute features
    feat["bar1_body"] = np.where(feat["bar1_open"] > 0,
                                  (feat["bar1_close"] - feat["bar1_open"]) / feat["bar1_open"], 0)
    feat["bar1_black"] = feat["bar1_body"] < 0
    feat["price_dir"] = np.where(feat["bar1_open"] > 0,
                                  (feat["close_0902"] - feat["bar1_open"]) / feat["bar1_open"], 0)

    # Historical median volume for this stock
    med_vol = feat["vol_3min"].median()
    feat["vol_vs_hist"] = feat["vol_3min"] / med_vol if med_vol > 0 else 1.0

    feat["stock_str"] = stock
    all_features.append(feat[["date","stock_str","bar1_open","bar1_close","bar1_body","bar1_black","price_dir","vol_3min","vol_vs_hist"]])

print("Concatenating features...")
feat_all = pd.concat(all_features, ignore_index=True)
print("Feature rows: %d" % len(feat_all))

# Merge with signals
sig_use = short[["date","stock_str","p","pred_q","adj_gap"]].copy()
merged = sig_use.merge(feat_all, on=["date","stock_str"], how="inner")
print("Matched signals: %d" % len(merged))

# === RESULTS ===
print("\n" + "="*70)
print("1. 第一根分K：黑K vs 紅K")
print("="*70)
for label, mask in [("黑K", merged["bar1_black"]), ("紅K", ~merged["bar1_black"])]:
    g = merged[mask]["p"]
    print("  %s: n=%d mean=%+.3f%% win=%.1f%%" % (label, len(g), g.mean()*100, (g>0).mean()*100))
t,p = stats.ttest_ind(merged[merged["bar1_black"]]["p"], merged[~merged["bar1_black"]]["p"], equal_var=False)
print("  t=%.2f p=%.2e" % (t,p))

print("\n" + "="*70)
print("2. 開盤量 vs 歷史中位（无前視）")
print("="*70)
bins_v = [0, 0.5, 1.0, 2.0, 4.0, 8.0, np.inf]
labels_v = ["<0.5x","0.5-1x","1-2x","2-4x","4-8x",">8x"]
merged["vol_b"] = pd.cut(merged["vol_vs_hist"], bins=bins_v, labels=labels_v)
for lbl in labels_v:
    g = merged[merged["vol_b"]==lbl]["p"]
    if len(g)<50: continue
    print("  %-8s n=%7d mean=%+.3f%% win=%.1f%%" % (lbl, len(g), g.mean()*100, (g>0).mean()*100))

print("\n" + "="*70)
print("3. 價格方向到09:02（无前視）")
print("="*70)
bins_pd = [-np.inf,-0.02,-0.01,-0.005,0.005,0.01,0.02,np.inf]
labels_pd = ["<-2%","-2~-1%","-1~-0.5%","flat","+0.5~1%","+1~2%",">2%"]
merged["pd_b"] = pd.cut(merged["price_dir"], bins=bins_pd, labels=labels_pd)
for lbl in labels_pd:
    g = merged[merged["pd_b"]==lbl]["p"]
    if len(g)<50: continue
    print("  %-12s n=%7d mean=%+.3f%% win=%.1f%%" % (lbl, len(g), g.mean()*100, (g>0).mean()*100))

print("\n" + "="*70)
print("4. 量價背離（无前視）")
print("="*70)
hv = merged["vol_vs_hist"] > 2.0
pd_ = merged["price_dir"] < -0.005
for label, mask in [("爆量+跌(竭盡)", hv&pd_), ("爆量+漲(動能)", hv&~pd_), ("正常+跌", ~hv&pd_), ("正常+漲", ~hv&~pd_)]:
    g = merged[mask]["p"]
    if len(g)<50: continue
    print("  %-18s n=%7d mean=%+.3f%% win=%.1f%%" % (label, len(g), g.mean()*100, (g>0).mean()*100))

print("\n" + "="*70)
print("5. 黑K+爆量 竭盡確認")
print("="*70)
exh = merged["bar1_black"] & (merged["vol_vs_hist"] > 2.0)
oth = ~exh
print("  黑K+爆量: n=%d mean=%+.3f%% win=%.1f%%" % (exh.sum(), merged[exh]["p"].mean()*100, (merged[exh]["p"]>0).mean()*100))
print("  Other:    n=%d mean=%+.3f%% win=%.1f%%" % (oth.sum(), merged[oth]["p"].mean()*100, (merged[oth]["p"]>0).mean()*100))
t2,p2 = stats.ttest_ind(merged[exh]["p"], merged[oth]["p"], equal_var=False)
print("  t=%.2f p=%.2e diff=%+.3f%%" % (t2, p2, (merged[exh]["p"].mean()-merged[oth]["p"].mean())*100))

print("\n" + "="*70)
print("6. 策略層（09:03 entry）")
print("="*70)
merged["p_adj"] = merged["p"] + merged["price_dir"]
print("  A: 09:00 all:      n=%d mean=%+.3f%%" % (len(merged), merged["p"].mean()*100))
print("  B: 09:03 all:      n=%d mean=%+.3f%%" % (len(merged), merged["p_adj"].mean()*100))
cb = merged[merged["bar1_black"]]["p_adj"]
print("  C: 09:03+黑K:      n=%d mean=%+.3f%% win=%.1f%%" % (len(cb), cb.mean()*100, (cb>0).mean()*100))
cd = merged[hv&pd_]["p_adj"]
print("  D: 09:03+量價背離: n=%d mean=%+.3f%% win=%.1f%%" % (len(cd), cd.mean()*100, (cd>0).mean()*100))

print("\n" + "="*70)
print("7. Spearman correlations")
print("="*70)
for col, lbl in [("bar1_body","bar1_body"),("vol_vs_hist","vol_vs_hist"),("price_dir","price_dir")]:
    v = merged[[col,"p"]].dropna()
    r,p = stats.spearmanr(v[col], v["p"])
    print("  %-15s rho=%+.4f p=%.2e n=%d" % (lbl, r, p, len(v)))

print("\nDone.")
