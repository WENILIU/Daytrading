import pandas as pd, numpy as np

df = pd.read_pickle('gap_fade_signals_2010.pkl')
df['date'] = pd.to_datetime(df['date'])
df['prev_close'] = df['entry'] / (1 + df['raw_gap'])

def get_tick(price):
    if price < 10: return 0.01
    elif price < 50: return 0.05
    elif price < 100: return 0.1
    elif price < 500: return 0.5
    else: return 1.0
def calc_zhangting(pc):
    raw = pc * 1.10; t = get_tick(pc); return int(raw / t) * t
def calc_dieding(pc):
    raw = pc * 0.90; t = get_tick(pc); return int(raw / t) * t + t

df['zhangting'] = df['prev_close'].apply(calc_zhangting)
df['dieding'] = df['prev_close'].apply(calc_dieding)
df['at_zhangting'] = (df['direction']=='SHORT') & np.isclose(df['entry'], df['zhangting'], rtol=0.002)
df['at_dieding'] = (df['direction']=='LONG') & np.isclose(df['entry'], df['dieding'], rtol=0.002)
df['at_limit'] = df['at_zhangting'] | df['at_dieding']
df = df[~df['at_limit']].copy()

COST = 0.0017; SL = 0.06; TP = 0.04

def sim(row):
    entry = row['entry']; d = row['direction']; hi = row['day_high']; lo = row['day_low']; cl = row['day_close']
    if d == 'SHORT':
        sl_p = entry*(1+SL); tp_p = entry*(1-TP)
        ep = sl_p if hi>=sl_p else (tp_p if lo<=tp_p else cl)
        return (entry-ep)/entry - 2*COST
    else:
        sl_p = entry*(1-SL); tp_p = entry*(1+TP)
        ep = sl_p if lo<=sl_p else (tp_p if hi>=tp_p else cl)
        return (ep-entry)/entry - 2*COST

df['pnl'] = df.apply(sim, axis=1)
df['win'] = (df['pnl'] > 0).astype(int)
df['year'] = df['date'].dt.year
df['abs_gap'] = df['adj_gap'].abs()

# === NEW FACTORS ===

# 1. Normalized gap (gap / stock's own volatility)
df = df.sort_values(['stock', 'date']).reset_index(drop=True)
df['prev_signal_close'] = df.groupby('stock')['prev_close'].shift(1)
df['stock_ret_1sig'] = (df['prev_close'] - df['prev_signal_close']) / df['prev_signal_close']
df['stock_vol'] = df.groupby('stock')['stock_ret_1sig'].transform(lambda x: x.rolling(5, min_periods=3).std())
df['norm_gap'] = df['abs_gap'] / (df['stock_vol'] + 0.001)  # Gap in units of stock vol

# 2. Gap rank among today's signals (1 = biggest gap)
df['gap_rank'] = df.groupby('date')['abs_gap'].rank(ascending=False)
df['gap_rank_pct'] = df['gap_rank'] / df.groupby('date')['abs_gap'].transform('count')

# 3. Sector correlation: count same-direction signals on same day (proxy for sector move)
daily_dir_count = df.groupby(['date', 'direction']).size().rename('same_dir_count').reset_index()
df = df.merge(daily_dir_count, on=['date', 'direction'], how='left')

# 4. Days since last signal for this stock (freshness)
df['days_since_last'] = (df['date'] - df.groupby('stock')['date'].shift(1)).dt.days

# 5. Market breadth (SHORT vs LONG ratio)
daily_short = df[df['direction']=='SHORT'].groupby('date').size().rename('n_short')
daily_long = df[df['direction']=='LONG'].groupby('date').size().rename('n_long')
df = df.merge(daily_short, on='date', how='left').merge(daily_long, on='date', how='left')
df['mkt_breadth'] = (df['n_short'].fillna(0) - df['n_long'].fillna(0)) / (df['n_short'].fillna(0) + df['n_long'].fillna(0) + 1)

# 6. Intraday range (volatility proxy - but this is outcome, check if predictable from gap)
df['day_range'] = (df['day_high'] - df['day_low']) / df['entry']

# 7. Gap vs price limits (how close to limit?)
df['gap_to_limit'] = np.where(df['direction']=='SHORT',
    (df['zhangting'] - df['entry']) / df['entry'],
    (df['entry'] - df['dieding']) / df['entry'])

# 8. Stock price level (proxy for retail vs institutional)
df['price_level'] = df['entry']

# 9. Consecutive gap days (stock gapped yesterday too?)
df['gapped_yesterday'] = (df.groupby('stock')['date'].shift(1).notna() & 
                          ((df['date'] - df.groupby('stock')['date'].shift(1)).dt.days == 1)).astype(int)

# 10. Signal time in sequence (first signals of the day vs later ones)
df['signal_order'] = df.groupby('date').cumcount() + 1

print('='*70)
print('ADDITIONAL FACTOR ANALYSIS')
print('='*70)
print('Baseline: %d trades, WR=%.1f%%, PnL=%+.3f%%' % (len(df), df['win'].mean()*100, df['pnl'].mean()*100))

# 1. Normalized gap
print('\n--- 1. Normalized Gap (gap / stock_vol) ---')
for lo, hi in [(0, 1), (1, 2), (2, 3), (3, 5), (5, 8), (8, 999)]:
    sub = df[(df['norm_gap'] >= lo) & (df['norm_gap'] < hi)]
    if len(sub) > 50:
        print('  NormGap %.0f-%.0fx: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo, hi, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 2. Gap rank
print('\n--- 2. Gap Rank (among today signals) ---')
for lo, hi in [(1, 3), (3, 5), (5, 8), (8, 12), (12, 20), (20, 999)]:
    sub = df[(df['gap_rank'] >= lo) & (df['gap_rank'] < hi)]
    if len(sub) > 50:
        print('  Rank %2d-%3d: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo, hi, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 3. Same direction count (sector move proxy)
print('\n--- 3. Same-Direction Signals Today (sector move proxy) ---')
for lo, hi in [(1, 3), (3, 5), (5, 8), (8, 12), (12, 20), (20, 999)]:
    sub = df[(df['same_dir_count'] >= lo) & (df['same_dir_count'] < hi)]
    if len(sub) > 50:
        print('  SameDir %2d-%3d: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo, hi, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 4. Days since last signal
print('\n--- 4. Days Since Last Signal (freshness) ---')
for lo, hi in [(0, 2), (2, 5), (5, 10), (10, 20), (20, 50), (50, 999)]:
    sub = df[(df['days_since_last'] >= lo) & (df['days_since_last'] < hi)]
    if len(sub) > 50:
        print('  %3d-%3d days: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo, hi, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 5. Market breadth
print('\n--- 5. Market Breadth (SHORT-LONG ratio) ---')
for lo, hi in [(-1, -0.5), (-0.5, -0.2), (-0.2, 0.2), (0.2, 0.5), (0.5, 1)]:
    sub = df[(df['mkt_breadth'] >= lo) & (df['mkt_breadth'] < hi)]
    if len(sub) > 50:
        print('  Breadth %+.1f to %+.1f: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo, hi, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 6. Gap to limit (how much room before hitting limit)
print('\n--- 6. Distance to Price Limit ---')
for lo, hi in [(0, 0.01), (0.01, 0.02), (0.02, 0.03), (0.03, 0.05), (0.05, 999)]:
    sub = df[(df['gap_to_limit'] >= lo) & (df['gap_to_limit'] < hi)]
    if len(sub) > 50:
        print('  ToLimit %.0f%%-%3.0f%%: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 7. Price level
print('\n--- 7. Stock Price Level ---')
for lo, hi in [(0, 20), (20, 35), (35, 50), (50, 100), (100, 200), (200, 99999)]:
    sub = df[(df['price_level'] >= lo) & (df['price_level'] < hi)]
    if len(sub) > 50:
        print('  Price %3d-%5d: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo, hi, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 8. Gapped yesterday
print('\n--- 8. Stock Gapped Yesterday (consecutive gap) ---')
for v in [0, 1]:
    sub = df[df['gapped_yesterday'] == v]
    label = 'Gapped yesterday' if v else 'No gap yesterday'
    print('  %s: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (label, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 9. Signal order in day
print('\n--- 9. Signal Order (first vs later in day) ---')
for lo, hi in [(1, 3), (3, 6), (6, 10), (10, 15), (15, 25), (25, 999)]:
    sub = df[(df['signal_order'] >= lo) & (df['signal_order'] < hi)]
    if len(sub) > 50:
        print('  Order %2d-%3d: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo, hi, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
