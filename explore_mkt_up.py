import pandas as pd
import numpy as np

df = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")
df["date"] = pd.to_datetime(df["date"])

print("=== Available columns ===")
print(df.columns.tolist())
print(f"\nTotal signals: {len(df)}")
print(f"Date range: {df['date'].min()} to {df['date'].max()}")

# Check what market_ret looks like
print(f"\n=== Market return distribution ===")
print(df["market_ret"].describe())

# Filter: market up > 2%
mkt_up = df[df["market_ret"] > 0.02]
print(f"\n=== Market > +2% subset ===")
print(f"Signals: {len(mkt_up)}")
print(f"Columns available: {mkt_up.columns.tolist()}")
print(f"\nSample row:")
print(mkt_up.iloc[0])
