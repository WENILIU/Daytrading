import pandas as pd
import numpy as np

df = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")
df["date"] = pd.to_datetime(df["date"])

# Simulate PnL for each trade (simplified: use day_close as exit if no SL/TP)
# Actually use the same logic as backtest: SL 6%, TP 4%
def simulate_pnl(row, sl=0.06, tp=0.04, cost=0.0017):
    entry = row["entry"]
    direction = row["direction"]
    hi = row["day_high"]
    lo = row["day_low"]
    cl = row["day_close"]
    
    if direction == "SHORT":
        sl_price = entry * (1 + sl)
        tp_price = entry * (1 - tp)
        if hi >= sl_price:
            exit_p = sl_price
        elif lo <= tp_price:
            exit_p = tp_price
        else:
            exit_p = cl
        return (entry - exit_p) / entry - 2*cost
    else:
        sl_price = entry * (1 - sl)
        tp_price = entry * (1 + tp)
        if lo <= sl_price:
            exit_p = sl_price
        elif hi >= tp_price:
            exit_p = tp_price
        else:
            exit_p = cl
        return (exit_p - entry) / entry - 2*cost

df["pnl"] = df.apply(simulate_pnl, axis=1)
df["win"] = (df["pnl"] > 0).astype(int)

# Intraday features (from OHLC)
df["range_pct"] = (df["day_high"] - df["day_low"]) / df["entry"]
df["close_vs_open"] = (df["day_close"] - df["entry"]) / df["entry"]
df["high_vs_open"] = (df["day_high"] - df["entry"]) / df["entry"]
df["low_vs_open"] = (df["day_low"] - df["entry"]) / df["entry"]

# Focus on market > 2% subset
mkt_up = df[df["market_ret"] > 0.02].copy()
print(f"=== Market > +2%: {len(mkt_up)} signals ===")
print(f"Overall win rate: {mkt_up['win'].mean()*100:.1f}%")
print(f"Avg PnL: {mkt_up['pnl'].mean()*100:.2f}%")

# Breakdown by direction
print(f"\n--- By Direction ---")
for d in ["SHORT", "LONG"]:
    sub = mkt_up[mkt_up["direction"] == d]
    print(f"  {d}: {len(sub)} signals, WR={sub['win'].mean()*100:.1f}%, avg={sub['pnl'].mean()*100:.2f}%")

# Breakdown by gap size
print(f"\n--- By Gap Size (SHORT only) ---")
short_up = mkt_up[mkt_up["direction"] == "SHORT"]
for lo, hi in [(0.05, 0.06), (0.06, 0.07), (0.07, 0.08), (0.08, 0.10), (0.10, 0.99)]:
    sub = short_up[(short_up["adj_gap"] >= lo) & (short_up["adj_gap"] < hi)]
    if len(sub) > 0:
        print(f"  Gap {lo*100:.0f}-{hi*100:.0f}%: {len(sub):>4} signals, WR={sub['win'].mean()*100:.1f}%, avg={sub['pnl'].mean()*100:.2f}%")

# KEY: Intraday pattern analysis (alpha mechanism)
print(f"\n--- Intraday Pattern (SHORT, market>2%) ---")
print("If alpha = retail overreaction, we expect: high early, then fade")
print(f"  Avg high vs open: {short_up['high_vs_open'].mean()*100:.2f}%")
print(f"  Avg low vs open:  {short_up['low_vs_open'].mean()*100:.2f}%")
print(f"  Avg close vs open: {short_up['close_vs_open'].mean()*100:.2f}%")

# Did the stock go HIGHER before dropping? (retail FOMO pattern)
went_higher = short_up[short_up["high_vs_open"] > 0.01]  # went up >1% after open
then_dropped = went_higher[went_higher["close_vs_open"] < -0.01]  # then dropped >1%
print(f"\n  Went up >1% then dropped >1%: {len(then_dropped)}/{len(short_up)} = {len(then_dropped)/len(short_up)*100:.1f}%")
print(f"  WR of this pattern: {then_dropped['win'].mean()*100:.1f}%")

# Did it drop immediately? (no retail FOMO)
dropped_immediately = short_up[short_up["low_vs_open"] < -0.02]  # dropped >2% from open
print(f"\n  Dropped >2% immediately: {len(dropped_immediately)}/{len(short_up)} = {len(dropped_immediately)/len(short_up)*100:.1f}%")
print(f"  WR of this pattern: {dropped_immediately['win'].mean()*100:.1f}%")

# Compare: market < -2% (opposite condition)
mkt_down = df[df["market_ret"] < -0.02].copy()
print(f"\n\n=== Market < -2%: {len(mkt_down)} signals ===")
print(f"Overall win rate: {mkt_down['win'].mean()*100:.1f}%")
print(f"Avg PnL: {mkt_down['pnl'].mean()*100:.2f}%")

# Compare SHORT in both conditions
short_down = mkt_down[mkt_down["direction"] == "SHORT"]
print(f"\n--- SHORT comparison ---")
print(f"  Market > +2%: WR={short_up['win'].mean()*100:.1f}%, avg={short_up['pnl'].mean()*100:.2f}%")
print(f"  Market < -2%: WR={short_down['win'].mean()*100:.1f}%, avg={short_down['pnl'].mean()*100:.2f}%")
