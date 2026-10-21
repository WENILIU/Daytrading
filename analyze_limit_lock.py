import pandas as pd
import numpy as np

sigs = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")

# Calculate actual SL/TP prices and check if they're reachable
# 漲停 = prev_close * 1.10, 跌停 = prev_close * 0.90
# (Most stocks have 10% limit; some ETFs/special cases differ but we filter those)

sigs['abs_gap'] = sigs['adj_gap'].abs()
sigs['raw_gap'] = sigs['raw_gap'] if 'raw_gap' in sigs.columns else sigs['adj_gap']

# For each trade, calculate:
# - SL price vs 漲停/跌停
# - TP price vs 漲停/跌停
# - Whether SL/TP is actually reachable

def analyze_trade(row):
    entry = row['entry']
    direction = row['direction']
    sl_pct, tp_pct = 0.06, 0.04
    
    # Estimate prev_close from entry and raw_gap
    # entry = prev_close * (1 + raw_gap) for SHORT (gap up)
    # entry = prev_close * (1 + raw_gap) for LONG (gap down, raw_gap < 0)
    # Actually: raw_gap = (open - prev_close) / prev_close
    # So prev_close = entry / (1 + raw_gap)
    raw_gap = row.get('raw_gap', row.get('adj_gap', 0))
    prev_close = entry / (1 + raw_gap) if (1 + raw_gap) != 0 else entry
    
    limit_up = prev_close * 1.10
    limit_down = prev_close * 0.90
    
    if direction == 'SHORT':
        sl_price = entry * (1 + sl_pct)
        tp_price = entry * (1 - tp_pct)
        
        # Can price reach SL? (price going UP)
        sl_reachable = sl_price <= limit_up
        # Can price reach TP? (price going DOWN)
        tp_reachable = tp_price >= limit_down
        
        # Max possible loss (at 漲停)
        max_loss_at_limit = (limit_up - entry) / entry if limit_up > entry else 0
        
        # Actual outcome
        hit_sl = row['day_high'] >= sl_price
        hit_tp = row['day_low'] <= tp_price
        
        return pd.Series({
            'sl_price': sl_price,
            'tp_price': tp_price,
            'limit_up': limit_up,
            'limit_down': limit_down,
            'sl_reachable': sl_reachable,
            'tp_reachable': tp_reachable,
            'max_loss_at_limit': max_loss_at_limit,
            'sl_hit': hit_sl,
            'tp_hit': hit_tp,
            'sl_beyond_limit': not sl_reachable,
        })
    else:  # LONG
        sl_price = entry * (1 - sl_pct)
        tp_price = entry * (1 + tp_pct)
        
        # Can price reach SL? (price going DOWN)
        sl_reachable = sl_price >= limit_down
        # Can price reach TP? (price going UP)
        tp_reachable = tp_price <= limit_up
        
        # Max possible loss (at 跌停)
        max_loss_at_limit = (entry - limit_down) / entry if entry > limit_down else 0
        
        hit_sl = row['day_low'] <= sl_price
        hit_tp = row['day_high'] >= tp_price
        
        return pd.Series({
            'sl_price': sl_price,
            'tp_price': tp_price,
            'limit_up': limit_up,
            'limit_down': limit_down,
            'sl_reachable': sl_reachable,
            'tp_reachable': tp_reachable,
            'max_loss_at_limit': max_loss_at_limit,
            'sl_hit': hit_sl,
            'tp_hit': hit_tp,
            'sl_beyond_limit': not sl_reachable,
        })

print("Analyzing 32k signals...")
results = sigs.apply(analyze_trade, axis=1)
sigs = pd.concat([sigs, results], axis=1)

# Top 15 per day
sigs_sorted = sigs.sort_values(['date', 'abs_gap'], ascending=[True, False])
sigs_top = sigs_sorted.groupby('date').head(15).copy()

print("=" * 80)
print("STOP LOSS REACHABILITY ANALYSIS")
print("=" * 80)

# Overall stats
total = len(sigs_top)
sl_unreachable = sigs_top['sl_beyond_limit'].sum()
print(f"\nTotal trades: {total}")
print(f"SL beyond price limit (unreachable): {sl_unreachable} ({sl_unreachable/total*100:.1f}%)")

# By direction
for d in ['SHORT', 'LONG']:
    subset = sigs_top[sigs_top['direction'] == d]
    n = len(subset)
    sl_unreach = subset['sl_beyond_limit'].sum()
    tp_unreach = (~subset['tp_reachable']).sum()
    print(f"\n--- {d} ({n} trades) ---")
    print(f"  SL unreachable (>漲停/跌停): {sl_unreach} ({sl_unreach/n*100:.1f}%)")
    print(f"  TP unreachable: {tp_unreach} ({tp_unreach/n*100:.1f}%)")
    
    # Max loss at price limit
    max_losses = subset['max_loss_at_limit']
    print(f"  Max loss at price limit: mean={max_losses.mean()*100:.2f}%, max={max_losses.max()*100:.2f}%")
    
    # By gap size
    bins = [0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 1.0]
    labels = ['5-6%', '6-7%', '7-8%', '8-9%', '9-10%', '>10%']
    subset_copy = subset.copy()
    subset_copy['gap_bucket'] = pd.cut(subset_copy['abs_gap'], bins=bins, labels=labels)
    
    stats = subset_copy.groupby('gap_bucket', observed=True).agg(
        count=('sl_beyond_limit', 'count'),
        sl_unreachable=('sl_beyond_limit', 'sum'),
        max_loss=('max_loss_at_limit', 'max'),
        avg_max_loss=('max_loss_at_limit', 'mean'),
    )
    stats['sl_unreach_pct'] = (stats['sl_unreachable'] / stats['count'] * 100).round(1)
    stats['max_loss'] = (stats['max_loss'] * 100).round(2)
    stats['avg_max_loss'] = (stats['avg_max_loss'] * 100).round(2)
    print(f"\n  {'Gap':<8} {'Count':>6} {'SL不可達%':>10} {'最大虧損%':>10} {'平均最大虧損%':>12}")
    for idx, row in stats.iterrows():
        print(f"  {str(idx):<8} {row['count']:>6.0f} {row['sl_unreach_pct']:>9.1f}% {row['max_loss']:>9.2f}% {row['avg_max_loss']:>11.2f}%")

# KEY INSIGHT: What actually happens when SL is unreachable?
print(f"\n{'='*80}")
print("ACTUAL OUTCOME WHEN SL UNREACHABLE")
print(f"{'='*80}")

unreachable = sigs_top[sigs_top['sl_beyond_limit']]
print(f"\nTrades where SL is beyond price limit: {len(unreachable)}")

# Calculate actual PnL for these trades
def actual_pnl(row):
    entry = row['entry']
    direction = row['direction']
    tp_pct = 0.04
    if direction == 'SHORT':
        tp_price = entry * (1 - tp_pct)
        hit_tp = row['day_low'] <= tp_price
        if hit_tp:
            return tp_pct
        else:
            return (entry - row['day_close']) / entry
    else:
        tp_price = entry * (1 + tp_pct)
        hit_tp = row['day_high'] >= tp_price
        if hit_tp:
            return tp_pct
        else:
            return (row['day_close'] - entry) / entry

unreachable_pnl = unreachable.apply(actual_pnl, axis=1)
print(f"  Win rate: {(unreachable_pnl > 0).mean()*100:.1f}%")
print(f"  Avg PnL: {unreachable_pnl.mean()*100:.2f}%")
print(f"  Worst loss: {unreachable_pnl.min()*100:.2f}%")
print(f"  P5 loss: {unreachable_pnl.quantile(0.05)*100:.2f}%")
print(f"  P1 loss: {unreachable_pnl.quantile(0.01)*100:.2f}%")

# Compare: what if we COULD stop at 6%?
print(f"\n  Hypothetical if SL worked at 6%:")
print(f"  Trades that would have been stopped: {(unreachable['sl_hit']).sum()}")
# But wait - if SL is unreachable, sl_hit should be False...
# Let me check: did day_high actually exceed sl_price?
sl_actually_hit = sigs_top[(sigs_top['sl_beyond_limit']) & (sigs_top['sl_hit'])]
print(f"  Contradictions (SL beyond limit but day_high > SL): {len(sl_actually_hit)}")

# The REAL question: what's the worst case scenario?
print(f"\n{'='*80}")
print("WORST CASE: Stock locked at 漲停/跌停 all day")
print(f"{'='*80}")

# For SHORT: stock opens +5%, goes to 漲停 (+10%), stays there
# Loss = (10% - 5%) / (1+5%) = 4.76%
# For SHORT: stock opens +9%, goes to 漲停 (+10%), stays there  
# Loss = (10% - 9%) / (1+9%) = 0.92%

# For LONG: stock opens -5%, goes to 跌停 (-10%), stays there
# Loss = (5% - (-10%)) / ... wait
# Entry at -5%, 跌停 at -10%: loss = (0.95 - 0.90) / 0.95 = 5.26%

# Let's find actual cases where stock hit limit and stayed
for d in ['SHORT', 'LONG']:
    subset = sigs_top[sigs_top['direction'] == d].copy()
    if d == 'SHORT':
        # Stock hit 漲停 (day_high very close to limit_up)
        hit_limit = subset[subset['day_high'] >= subset['limit_up'] * 0.999]
    else:
        # Stock hit 跌停 (day_low very close to limit_down)
        hit_limit = subset[subset['day_low'] <= subset['limit_down'] * 1.001]
    
    if len(hit_limit) > 0:
        pnl = hit_limit.apply(actual_pnl, axis=1)
        print(f"\n{d}: Hit price limit: {len(hit_limit)} trades")
        print(f"  Avg PnL: {pnl.mean()*100:.2f}%")
        print(f"  Worst: {pnl.min()*100:.2f}%")
        print(f"  WR: {(pnl>0).mean()*100:.1f}%")
