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

# A group only
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
df['month'] = df['date'].dt.month
df['weekday'] = df['date'].dt.dayofweek  # 0=Mon, 4=Fri

# Features
df['abs_gap'] = df['adj_gap'].abs()
df['intraday_range'] = (df['day_high'] - df['day_low']) / df['entry']
df['close_vs_open'] = (df['day_close'] - df['entry']) / df['entry']  # negative = dropped (good for SHORT)
df['gap_vs_range'] = df['abs_gap'] / (df['intraday_range'] + 0.001)  # gap size relative to day range

# Signal count per day
daily_count = df.groupby('date').size().rename('signals_today')
df = df.merge(daily_count, on='date', how='left')

# Previous day market return (lagged)
# We need to reconstruct market data - use the market_ret column
# Get unique dates and their market returns
market_daily = df.groupby('date')['market_ret'].first().sort_index()
market_daily_lag = market_daily.shift(1)
df['prev_market_ret'] = df['date'].map(market_daily_lag)

# 2-day cumulative market return
market_daily_lag2 = market_daily.shift(1) + market_daily.shift(2)
df['prev2_market_ret'] = df['date'].map(market_daily_lag2)

# Consecutive gap days for same stock (check if stock had signal yesterday)
df = df.sort_values(['stock', 'date'])
df['prev_signal_date'] = df.groupby('stock')['date'].shift(1)
df['days_since_last_signal'] = (df['date'] - df['prev_signal_date']).dt.days
df['had_signal_yesterday'] = (df['days_since_last_signal'] == 1).astype(int)

print('='*70)
print('A GROUP OPTIMIZATION ANALYSIS')
print('='*70)
print('Baseline: %d trades, WR=%.1f%%, AvgPnL=%+.3f%%' % (len(df), df['win'].mean()*100, df['pnl'].mean()*100))
print()

# ============================================================
# 1. DAY OF WEEK
# ============================================================
print('='*70)
print('1. DAY OF WEEK EFFECT')
print('='*70)
day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
for dow in range(5):
    sub = df[df['weekday']==dow]
    if len(sub) > 0:
        print('  %s: n=%5d, WR=%.1f%%, AvgPnL=%+.3f%%' % (day_names[dow], len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
print()

# By direction
print('  By direction:')
for d in ['SHORT', 'LONG']:
    print('    %s:' % d)
    for dow in range(5):
        sub = df[(df['weekday']==dow) & (df['direction']==d)]
        if len(sub) > 0:
            print('      %s: n=%5d, WR=%.1f%%, AvgPnL=%+.3f%%' % (day_names[dow], len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
print()

# ============================================================
# 2. MARKET ENVIRONMENT (previous day)
# ============================================================
print('='*70)
print('2. PREVIOUS DAY MARKET RETURN')
print('='*70)
valid = df.dropna(subset=['prev_market_ret'])
bins = [(-999, -0.03), (-0.03, -0.02), (-0.02, -0.01), (-0.01, 0), (0, 0.01), (0.01, 0.02), (0.02, 0.03), (0.03, 999)]
for lo, hi in bins:
    sub = valid[(valid['prev_market_ret'] >= lo) & (valid['prev_market_ret'] < hi)]
    if len(sub) > 0:
        label = '%.1f%% to %.1f%%' % (lo*100, hi*100)
        print('  Prev mkt %15s: n=%5d, WR=%.1f%%, AvgPnL=%+.3f%%' % (label, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
print()

# ============================================================
# 3. GAP SIZE
# ============================================================
print('='*70)
print('3. GAP SIZE (adj_gap)')
print('='*70)
gap_bins = [(0.05, 0.06), (0.06, 0.07), (0.07, 0.08), (0.08, 0.10), (0.10, 0.15), (0.15, 999)]
for lo, hi in gap_bins:
    sub = df[(df['abs_gap'] >= lo) & (df['abs_gap'] < hi)]
    if len(sub) > 0:
        print('  Gap %2.0f%%-%2.0f%%: n=%5d, WR=%.1f%%, AvgPnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
print()

# ============================================================
# 4. SIGNALS PER DAY (crowding)
# ============================================================
print('='*70)
print('4. SIGNALS PER DAY (crowding effect)')
print('='*70)
for n in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
    sub = df[df['signals_today'] == n]
    if len(sub) > 0:
        print('  %2d signals/day: n=%5d, WR=%.1f%%, AvgPnL=%+.3f%%' % (n, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
sub = df[df['signals_today'] >= 11]
if len(sub) > 0:
    print('  11+ signals/day: n=%5d, WR=%.1f%%, AvgPnL=%+.3f%%' % (len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
print()

# ============================================================
# 5. REPEAT SIGNAL (same stock had signal yesterday)
# ============================================================
print('='*70)
print('5. REPEAT SIGNAL (same stock consecutive days)')
print('='*70)
for v in [0, 1]:
    sub = df[df['had_signal_yesterday'] == v]
    label = 'Had signal yesterday' if v else 'No signal yesterday'
    print('  %s: n=%5d, WR=%.1f%%, AvgPnL=%+.3f%%' % (label, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
print()

# ============================================================
# 6. MONTH SEASONALITY
# ============================================================
print('='*70)
print('6. MONTH SEASONALITY')
print('='*70)
for m in range(1, 13):
    sub = df[df['month'] == m]
    if len(sub) > 0:
        print('  Month %2d: n=%5d, WR=%.1f%%, AvgPnL=%+.3f%%' % (m, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
print()

# ============================================================
# 7. INTRADAY RANGE (volatility proxy)
# ============================================================
print('='*70)
print('7. INTRADAY RANGE (day_high-day_low)/entry')
print('='*70)
range_bins = [(0, 0.03), (0.03, 0.05), (0.05, 0.07), (0.07, 0.10), (0.10, 0.15), (0.15, 999)]
for lo, hi in range_bins:
    sub = df[(df['intraday_range'] >= lo) & (df['intraday_range'] < hi)]
    if len(sub) > 0:
        print('  Range %2.0f%%-%3.0f%%: n=%5d, WR=%.1f%%, AvgPnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
print()

# ============================================================
# 8. 2-DAY MARKET MOMENTUM
# ============================================================
print('='*70)
print('8. 2-DAY CUMULATIVE MARKET RETURN (before today)')
print('='*70)
valid2 = df.dropna(subset=['prev2_market_ret'])
for lo, hi in [(-999, -0.05), (-0.05, -0.03), (-0.03, -0.01), (-0.01, 0.01), (0.01, 0.03), (0.03, 0.05), (0.05, 999)]:
    sub = valid2[(valid2['prev2_market_ret'] >= lo) & (valid2['prev2_market_ret'] < hi)]
    if len(sub) > 0:
        print('  2d mkt %+5.1f%% to %+5.1f%%: n=%5d, WR=%.1f%%, AvgPnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
