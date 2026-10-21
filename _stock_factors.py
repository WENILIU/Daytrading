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

# === STOCK-LEVEL FEATURES ===
# Sort by stock and date to compute per-stock features
df = df.sort_values(['stock', 'date']).reset_index(drop=True)

# Stock price trend: return over recent signal history
# prev_close is yesterday's close. Between signals, we don't have data.
# But we can compute: how has prev_close changed across recent signals?
# This approximates the stock's recent trend.

# Stock return from previous signal to current (gap between signals)
df['prev_signal_close'] = df.groupby('stock')['prev_close'].shift(1)
df['stock_ret_between_signals'] = (df['prev_close'] - df['prev_signal_close']) / df['prev_signal_close']

# Stock 3-signal trend (cumulative return over last 3 signal appearances)
df['prev_signal_close_3'] = df.groupby('stock')['prev_close'].shift(3)
df['stock_ret_3sig'] = (df['prev_close'] - df['prev_signal_close_3']) / df['prev_signal_close_3']

# Stock drawdown from recent high (max prev_close in last 5 signals)
df['stock_high_5'] = df.groupby('stock')['prev_close'].transform(lambda x: x.rolling(5, min_periods=2).max())
df['stock_drawdown'] = (df['prev_close'] - df['stock_high_5']) / df['stock_high_5']

# Stock volatility (std of returns between signals, last 5)
df['stock_vol'] = df.groupby('stock')['stock_ret_between_signals'].transform(lambda x: x.rolling(5, min_periods=3).std())

# Stock signal frequency (how many times appeared in last 30 days)
df['stock_signals_30d'] = 0
for idx in df.index:
    stock = df.at[idx, 'stock']
    date = df.at[idx, 'date']
    cutoff = date - pd.Timedelta(days=30)
    count = ((df['stock'] == stock) & (df['date'] >= cutoff) & (df['date'] < date)).sum()
    df.at[idx, 'stock_signals_30d'] = count

# Stock last signal PnL
df['stock_last_pnl'] = df.groupby('stock')['pnl'].shift(1)

# Stock consecutive gap direction (same direction signals in a row)
df['same_dir_streak'] = 0
for stock, group in df.groupby('stock'):
    streak = 0
    prev_dir = None
    for idx in group.index:
        curr_dir = df.at[idx, 'direction']
        if curr_dir == prev_dir:
            streak += 1
        else:
            streak = 1
        df.at[idx, 'same_dir_streak'] = streak
        prev_dir = curr_dir

# Stock intraday range (volatility proxy from signal day itself)
df['stock_day_range'] = (df['day_high'] - df['day_low']) / df['entry']

# === ANALYSIS ===
print('='*70)
print('STOCK-LEVEL FACTOR ANALYSIS')
print('='*70)
print('Baseline: %d trades, WR=%.1f%%, PnL=%+.3f%%' % (len(df), df['win'].mean()*100, df['pnl'].mean()*100))
print()

# 1. Stock trend (return between signals)
print('--- 1. Stock Trend (return between last 2 signals) ---')
for lo, hi in [(-999, -0.10), (-0.10, -0.05), (-0.05, -0.02), (-0.02, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 999)]:
    sub = df[(df['stock_ret_between_signals'] >= lo) & (df['stock_ret_between_signals'] < hi)]
    if len(sub) > 50:
        print('  Stock %+.0f%% to %+.0f%%: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 2. Stock drawdown from recent high
print('\n--- 2. Stock Drawdown from 5-signal High ---')
for lo, hi in [(-999, -0.15), (-0.15, -0.10), (-0.10, -0.05), (-0.05, -0.02), (-0.02, 0.0), (0.0, 999)]:
    sub = df[(df['stock_drawdown'] >= lo) & (df['stock_drawdown'] < hi)]
    if len(sub) > 50:
        print('  Stock DD %+.0f%% to %+.0f%%: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 3. Stock volatility
print('\n--- 3. Stock Volatility (between signals) ---')
for lo, hi in [(0, 0.02), (0.02, 0.05), (0.05, 0.08), (0.08, 0.12), (0.12, 999)]:
    sub = df[(df['stock_vol'] >= lo) & (df['stock_vol'] < hi)]
    if len(sub) > 50:
        print('  Stock Vol %.0f%%-%.0f%%: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 4. Stock signal frequency (repeat offender)
print('\n--- 4. Stock Signal Frequency (last 30d) ---')
for n in range(0, 6):
    sub = df[df['stock_signals_30d'] == n]
    if len(sub) > 50:
        print('  %d prior signals/30d: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (n, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
sub = df[df['stock_signals_30d'] >= 6]
if len(sub) > 50:
    print('  6+ prior signals/30d: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 5. Last signal PnL (did it work last time?)
print('\n--- 5. Last Signal PnL (same stock) ---')
for lo, hi in [(-999, -0.03), (-0.03, 0), (0, 0.03), (0.03, 999)]:
    sub = df[(df['stock_last_pnl'] >= lo) & (df['stock_last_pnl'] < hi)]
    if len(sub) > 50:
        print('  Last PnL %+.0f%% to %+.0f%%: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 6. Same direction streak
print('\n--- 6. Same Direction Streak (consecutive same-direction signals) ---')
for n in range(1, 6):
    sub = df[df['same_dir_streak'] == n]
    if len(sub) > 50:
        print('  Streak %d: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (n, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
sub = df[df['same_dir_streak'] >= 6]
if len(sub) > 50:
    print('  Streak 6+: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 7. Stock 3-signal trend
print('\n--- 7. Stock 3-Signal Cumulative Return ---')
for lo, hi in [(-999, -0.15), (-0.15, -0.08), (-0.08, -0.03), (-0.03, 0.03), (0.03, 0.08), (0.08, 0.15), (0.15, 999)]:
    sub = df[(df['stock_ret_3sig'] >= lo) & (df['stock_ret_3sig'] < hi)]
    if len(sub) > 50:
        print('  3sig ret %+.0f%% to %+.0f%%: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 8. By direction: does stock trend matter differently for LONG vs SHORT?
print('\n--- 8. Stock Trend by Direction ---')
for d in ['SHORT', 'LONG']:
    print('  %s:' % d)
    for lo, hi in [(-999, -0.05), (-0.05, -0.02), (-0.02, 0.02), (0.02, 0.05), (0.05, 999)]:
        sub = df[(df['direction']==d) & (df['stock_ret_between_signals'] >= lo) & (df['stock_ret_between_signals'] < hi)]
        if len(sub) > 50:
            print('    Stock %+.0f%% to %+.0f%%: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
