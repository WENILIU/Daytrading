import pandas as pd
import numpy as np

# Load signals
sigs = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")

# Calculate PnL for each trade (SHORT: profit when price drops, LONG: profit when price rises)
# Using SL6/TP4 as in Plan B
def calc_pnl(row):
    entry = row['entry']
    direction = row['direction']
    sl_pct = 0.06
    tp_pct = 0.04
    
    if direction == 'SHORT':
        sl_price = entry * (1 + sl_pct)
        tp_price = entry * (1 - tp_pct)
        # Check if TP hit first (day_low <= tp_price) or SL hit first (day_high >= sl_price)
        hit_tp = row['day_low'] <= tp_price
        hit_sl = row['day_high'] >= sl_price
        if hit_tp and hit_sl:
            # Ambiguous - use close to determine
            if row['day_close'] < entry:
                return tp_pct
            else:
                return -sl_pct
        elif hit_tp:
            return tp_pct
        elif hit_sl:
            return -sl_pct
        else:
            # Force close at day_close
            return (entry - row['day_close']) / entry
    else:  # LONG
        sl_price = entry * (1 - sl_pct)
        tp_price = entry * (1 + tp_pct)
        hit_tp = row['day_high'] >= tp_price
        hit_sl = row['day_low'] <= sl_price
        if hit_tp and hit_sl:
            if row['day_close'] > entry:
                return tp_pct
            else:
                return -sl_pct
        elif hit_tp:
            return tp_pct
        elif hit_sl:
            return -sl_pct
        else:
            return (row['day_close'] - entry) / entry

sigs['pnl'] = sigs.apply(calc_pnl, axis=1)
sigs['abs_gap'] = sigs['adj_gap'].abs()
sigs['win'] = (sigs['pnl'] > 0).astype(int)

# Deduplicate: keep top 15 per day by abs_gap (matching strategy)
sigs_sorted = sigs.sort_values(['date', 'abs_gap'], ascending=[True, False])
sigs_top = sigs_sorted.groupby('date').head(15).copy()

print("=" * 70)
print("WIN RATE BY GAP SIZE (after top-15 filter)")
print("=" * 70)

# Granular gap buckets
bins = [0.05, 0.055, 0.06, 0.065, 0.07, 0.08, 0.09, 0.10, 0.15, 0.20, 1.0]
labels = ['5.0-5.5%', '5.5-6.0%', '6.0-6.5%', '6.5-7.0%', '7.0-8.0%', 
          '8.0-9.0%', '9.0-10%', '10-15%', '15-20%', '>20%']
sigs_top['gap_bucket'] = pd.cut(sigs_top['abs_gap'], bins=bins, labels=labels)

stats = sigs_top.groupby('gap_bucket', observed=True).agg(
    count=('pnl', 'count'),
    win_rate=('win', 'mean'),
    avg_pnl=('pnl', 'mean'),
    median_pnl=('pnl', 'median'),
    std_pnl=('pnl', 'std'),
    sharpe_per_trade=('pnl', lambda x: x.mean() / x.std() if x.std() > 0 else 0)
).round(4)

print(stats.to_string())
print(f"\nTotal trades: {len(sigs_top)}")

# Also check by direction
print("\n" + "=" * 70)
print("WIN RATE BY GAP SIZE x DIRECTION")
print("=" * 70)

for d in ['SHORT', 'LONG']:
    subset = sigs_top[sigs_top['direction'] == d]
    stats_d = subset.groupby('gap_bucket', observed=True).agg(
        count=('pnl', 'count'),
        win_rate=('win', 'mean'),
        avg_pnl=('pnl', 'mean'),
    ).round(4)
    print(f"\n--- {d} ---")
    print(stats_d.to_string())

# Check: what if we size by expected value?
print("\n" + "=" * 70)
print("EXPECTED VALUE PER TRADE (for Kelly-like sizing)")
print("=" * 70)

ev = sigs_top.groupby('gap_bucket', observed=True).agg(
    count=('pnl', 'count'),
    win_rate=('win', 'mean'),
    avg_win=('pnl', lambda x: x[x>0].mean() if (x>0).any() else 0),
    avg_loss=('pnl', lambda x: x[x<=0].mean() if (x<=0).any() else 0),
).round(4)
ev['expected_value'] = ev['win_rate'] * ev['avg_win'] + (1-ev['win_rate']) * ev['avg_loss']
ev['kelly_fraction'] = ev['expected_value'] / (ev['avg_win'].abs() + ev['avg_loss'].abs())
print(ev.to_string())
