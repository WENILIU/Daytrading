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
df['month'] = df['date'].dt.month
df['weekday'] = df['date'].dt.dayofweek
df['abs_gap'] = df['adj_gap'].abs()

# === MARKET FEATURES ===
market_daily = df.groupby('date')['market_ret'].first().sort_index()
df['prev_market_ret'] = df['date'].map(market_daily.shift(1))
df['prev2_market_ret'] = df['date'].map((market_daily.shift(1) + market_daily.shift(2)))
df['prev3_market_ret'] = df['date'].map((market_daily.shift(1) + market_daily.shift(2) + market_daily.shift(3)))

# Market volatility (rolling std of market returns, 5 days)
mkt_vol = market_daily.rolling(5).std()
df['mkt_vol_5d'] = df['date'].map(mkt_vol.shift(1))

# Market drawdown from 20-day high
mkt_cum = (1 + market_daily).cumprod()
mkt_high_20 = mkt_cum.rolling(20).max()
mkt_dd = (mkt_cum - mkt_high_20) / mkt_high_20
df['mkt_drawdown'] = df['date'].map(mkt_dd.shift(1))

# Consecutive market down days
def count_consecutive_down(series):
    result = pd.Series(0, index=series.index)
    count = 0
    for i, v in enumerate(series.values):
        if v < 0:
            count += 1
        else:
            count = 0
        result.iloc[i] = count
    return result

consec_down = count_consecutive_down(market_daily)
df['consec_down_days'] = df['date'].map(consec_down.shift(1))

# === SIGNAL FEATURES ===
daily_count = df.groupby('date').size().rename('signals_today')
df = df.merge(daily_count, on='date', how='left')

# Direction ratio (SHORT vs LONG signals today)
daily_short = df[df['direction']=='SHORT'].groupby('date').size().rename('short_count')
df = df.merge(daily_short, on='date', how='left')
df['short_ratio'] = df['short_count'] / df['signals_today']

# Same stock previous day performance
df = df.sort_values(['stock', 'date'])
df['prev_stock_ret'] = df.groupby('stock')['day_close'].pct_change()  # This is prev_close/prev_prev_close - 1... not quite
# Actually let's get: did the stock go up or down yesterday?
# We have prev_close and entry (= today's open). prev_close IS yesterday's close.
# We need yesterday's open to know yesterday's direction. We don't have it directly.
# But we can check: was there a signal for this stock yesterday? If so, what was its direction?
df['prev_signal_date'] = df.groupby('stock')['date'].shift(1)
df['days_since_last'] = (df['date'] - df['prev_signal_date']).dt.days
df['had_signal_yesterday'] = (df['days_since_last'] == 1).astype(int)

# Stock price level (proxy for stock type)
df['price_level'] = df['entry']

# Gap direction consistency with market (gap up in down market = stronger reversal signal)
df['gap_mkt_alignment'] = 0
# SHORT (gap up) in down market = misaligned = stronger reversal
df.loc[(df['direction']=='SHORT') & (df['prev_market_ret'] < 0), 'gap_mkt_alignment'] = 1
# LONG (gap down) in up market = misaligned = stronger reversal  
df.loc[(df['direction']=='LONG') & (df['prev_market_ret'] > 0), 'gap_mkt_alignment'] = 1

print('='*70)
print('ADDITIONAL FACTOR ANALYSIS')
print('='*70)

# 1. Market volatility (5d rolling std)
print('\n--- Market Volatility (5d, prev day) ---')
for lo, hi in [(0, 0.005), (0.005, 0.01), (0.01, 0.015), (0.015, 0.02), (0.02, 0.03), (0.03, 999)]:
    sub = df[(df['mkt_vol_5d'] >= lo) & (df['mkt_vol_5d'] < hi)]
    if len(sub) > 50:
        print('  Vol %.1f%%-%.1f%%: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 2. Market drawdown
print('\n--- Market Drawdown from 20d High ---')
for lo, hi in [(-999, -0.10), (-0.10, -0.05), (-0.05, -0.03), (-0.03, -0.01), (-0.01, 0), (0, 999)]:
    sub = df[(df['mkt_drawdown'] >= lo) & (df['mkt_drawdown'] < hi)]
    if len(sub) > 50:
        print('  DD %5.1f%% to %5.1f%%: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 3. Consecutive down days
print('\n--- Consecutive Market Down Days ---')
for n in range(0, 6):
    sub = df[df['consec_down_days'] == n]
    if len(sub) > 50:
        print('  %d down days: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (n, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 4. Gap-market alignment
print('\n--- Gap vs Market Direction ---')
for v in [0, 1]:
    sub = df[df['gap_mkt_alignment'] == v]
    label = 'Gap opposite to mkt (misaligned)' if v else 'Gap same as mkt (aligned)'
    print('  %s: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (label, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 5. Short ratio (market sentiment proxy)
print('\n--- Short Signal Ratio (market fear proxy) ---')
for lo, hi in [(0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]:
    sub = df[(df['short_ratio'] >= lo) & (df['short_ratio'] < hi)]
    if len(sub) > 50:
        print('  Short ratio %.0f%%-%.0f%%: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 6. Stock price level
print('\n--- Stock Price Level ---')
for lo, hi in [(0, 30), (30, 50), (50, 100), (100, 200), (200, 500), (500, 99999)]:
    sub = df[(df['price_level'] >= lo) & (df['price_level'] < hi)]
    if len(sub) > 50:
        print('  Price %4d-%5d: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo, hi, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))

# 7. 3-day market cumulative
print('\n--- 3-Day Market Cumulative Return ---')
valid3 = df.dropna(subset=['prev3_market_ret'])
for lo, hi in [(-999, -0.05), (-0.05, -0.03), (-0.03, -0.01), (-0.01, 0.01), (0.01, 0.03), (0.03, 0.05), (0.05, 999)]:
    sub = valid3[(valid3['prev3_market_ret'] >= lo) & (valid3['prev3_market_ret'] < hi)]
    if len(sub) > 50:
        print('  3d mkt %+5.1f%% to %+5.1f%%: n=%5d, WR=%.1f%%, PnL=%+.3f%%' % (lo*100, hi*100, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
