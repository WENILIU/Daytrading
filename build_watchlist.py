import pandas as pd
from datetime import timedelta

df = pd.read_pickle("gap_fade_signals_2010.pkl")
df["date"] = pd.to_datetime(df["date"])

# Use last 90 days for watchlist
cutoff = df["date"].max() - timedelta(days=90)
recent = df[df["date"] >= cutoff]
n_stocks = recent["stock"].nunique()
print(f"Recent 90d signals: {len(recent)} from {n_stocks} stocks")

freq = recent.groupby("stock").size().sort_values(ascending=False)

for n in [50, 100, 140, 200, 300]:
    top = freq.head(n)
    coverage = top.sum() / freq.sum() * 100
    print(f"  Top {n:3d}: covers {coverage:.1f}%")

watchlist = freq.head(140).index.tolist()
with open("watchlist.txt", "w") as f:
    f.write("\n".join(watchlist))
print(f"\nSaved watchlist.txt: {len(watchlist)} stocks")
