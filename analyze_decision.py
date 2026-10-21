import pandas as pd, numpy as np

df = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")
df["date"] = pd.to_datetime(df["date"])

def simulate_pnl(row, sl=0.06, tp=0.04, cost=0.0017):
    entry=row["entry"]; d=row["direction"]; hi=row["day_high"]; lo=row["day_low"]; cl=row["day_close"]
    if d=="SHORT":
        sl_p=entry*(1+sl); tp_p=entry*(1-tp)
        ep = sl_p if hi>=sl_p else (tp_p if lo<=tp_p else cl)
        return (entry-ep)/entry - 2*cost
    else:
        sl_p=entry*(1-sl); tp_p=entry*(1+tp)
        ep = sl_p if lo<=sl_p else (tp_p if hi>=tp_p else cl)
        return (ep-entry)/entry - 2*cost

df["pnl"] = df.apply(simulate_pnl, axis=1)
df["win"] = (df["pnl"] > 0).astype(int)

# Features from daily OHLC
df["low_vs_open"] = (df["day_low"] - df["entry"]) / df["entry"]
df["high_vs_open"] = (df["day_high"] - df["entry"]) / df["entry"]
df["close_vs_open"] = (df["day_close"] - df["entry"]) / df["entry"]
df["range"] = (df["day_high"] - df["day_low"]) / df["entry"]

# Market > 2% SHORT
mkt_up_short = df[(df["market_ret"] > 0.02) & (df["direction"] == "SHORT")].copy()
print(f"=== Market>2% SHORT: {len(mkt_up_short)} signals ===")
print(f"Baseline: WR={mkt_up_short['win'].mean()*100:.1f}%, avg={mkt_up_short['pnl'].mean()*100:.2f}%")

# KEY INSIGHT: Can we predict from the gap itself?
print(f"\n--- Gap Size (the only 9:00 feature we have) ---")
for lo, hi in [(0.05,0.06),(0.06,0.07),(0.07,0.08),(0.08,0.10),(0.10,0.99)]:
    sub = mkt_up_short[(mkt_up_short["adj_gap"]>=lo)&(mkt_up_short["adj_gap"]<hi)]
    if len(sub)>=5:
        print(f"  Gap {lo*100:.0f}-{hi*100:.0f}%: {len(sub):>3}, WR={sub['win'].mean()*100:.1f}%, avg={sub['pnl'].mean()*100:.2f}%")

# Market return magnitude
print(f"\n--- Market Return Magnitude ---")
for lo, hi in [(0.02,0.03),(0.03,0.05),(0.05,0.99)]:
    sub = df[(df["market_ret"]>=lo)&(df["market_ret"]<hi)&(df["direction"]=="SHORT")]
    if len(sub)>=5:
        print(f"  Mkt +{lo*100:.0f}-{hi*100:.0f}%: {len(sub):>3}, WR={sub['win'].mean()*100:.1f}%, avg={sub['pnl'].mean()*100:.2f}%")

# What about LONG in market>2%? (the user might want to flip direction)
mkt_up_long = df[(df["market_ret"] > 0.02) & (df["direction"] == "LONG")].copy()
print(f"\n=== Market>2% LONG: {len(mkt_up_long)} signals ===")
print(f"WR={mkt_up_long['win'].mean()*100:.1f}%, avg={mkt_up_long['pnl'].mean()*100:.2f}%")

# The REAL question: should we SKIP SHORT when market>2%?
print(f"\n\n=== DECISION ANALYSIS: Skip SHORT when market>2%? ===")
all_short = df[df["direction"]=="SHORT"]
normal_short = all_short[all_short["market_ret"] <= 0.02]
print(f"All SHORT: {len(all_short)}, WR={all_short['win'].mean()*100:.1f}%, avg={all_short['pnl'].mean()*100:.2f}%")
print(f"SHORT (mkt<=2%): {len(normal_short)}, WR={normal_short['win'].mean()*100:.1f}%, avg={normal_short['pnl'].mean()*100:.2f}%")
print(f"SHORT (mkt>2%): {len(mkt_up_short)}, WR={mkt_up_short['win'].mean()*100:.1f}%, avg={mkt_up_short['pnl'].mean()*100:.2f}%")

# Impact of skipping
total_pnl_with = all_short["pnl"].sum()
total_pnl_without = normal_short["pnl"].sum()
print(f"\nTotal PnL with all SHORT: {total_pnl_with:.1f}")
print(f"Total PnL skip mkt>2%:    {total_pnl_without:.1f}")
print(f"Difference: {total_pnl_without - total_pnl_with:.1f} (skipping {'HELPS' if total_pnl_without > total_pnl_with else 'HURTS'})")

# But: LONG in market>2% is profitable!
print(f"\n=== OPPORTUNITY: LONG in market>2% ===")
print(f"LONG (mkt>2%): {len(mkt_up_long)}, WR={mkt_up_long['win'].mean()*100:.1f}%, avg={mkt_up_long['pnl'].mean()*100:.2f}%")
print(f"Total PnL from LONG mkt>2%: {mkt_up_long['pnl'].sum():.1f}")
