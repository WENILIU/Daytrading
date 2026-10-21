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

# Market features
market_daily = df.groupby('date')['market_ret'].first().sort_index()
df['prev_market_ret'] = df['date'].map(market_daily.shift(1))
df['prev3_market_ret'] = df['date'].map((market_daily.shift(1) + market_daily.shift(2) + market_daily.shift(3)))
mkt_vol = market_daily.rolling(5).std()
df['mkt_vol_5d'] = df['date'].map(mkt_vol.shift(1))
mkt_cum = (1 + market_daily).cumprod()
mkt_high_20 = mkt_cum.rolling(20).max()
mkt_dd = (mkt_cum - mkt_high_20) / mkt_high_20
df['mkt_drawdown'] = df['date'].map(mkt_dd.shift(1))

def count_consecutive_down(series):
    result = pd.Series(0, index=series.index)
    count = 0
    for i, v in enumerate(series.values):
        if v < 0: count += 1
        else: count = 0
        result.iloc[i] = count
    return result
consec_down = count_consecutive_down(market_daily)
df['consec_down_days'] = df['date'].map(consec_down.shift(1))

daily_count = df.groupby('date').size().rename('signals_today')
df = df.merge(daily_count, on='date', how='left')

# Stock features
df = df.sort_values(['stock', 'date']).reset_index(drop=True)
df['prev_signal_close'] = df.groupby('stock')['prev_close'].shift(1)
df['stock_ret_1sig'] = (df['prev_close'] - df['prev_signal_close']) / df['prev_signal_close']

df['stock_high_5'] = df.groupby('stock')['prev_close'].transform(lambda x: x.rolling(5, min_periods=2).max())
df['stock_drawdown'] = (df['prev_close'] - df['stock_high_5']) / df['stock_high_5']

# Signal count in last 30 days (vectorized)
df['stock_signals_30d'] = 0
for stock, grp in df.groupby('stock'):
    dates = grp['date'].values
    indices = grp.index.values
    for i in range(len(dates)):
        cutoff = dates[i] - np.timedelta64(30, 'D')
        count = np.sum((dates[:i] >= cutoff))
        df.at[indices[i], 'stock_signals_30d'] = count

# Repeat signal yesterday
df['prev_signal_date'] = df.groupby('stock')['date'].shift(1)
df['had_signal_yesterday'] = ((df['date'] - df['prev_signal_date']).dt.days == 1).astype(int)

# === BUILD SCORES ===
# Market score (same as Model B)
df['mkt_score'] = 0
df.loc[df['mkt_drawdown'] < -0.10, 'mkt_score'] += 4
df.loc[(df['mkt_drawdown'] >= -0.10) & (df['mkt_drawdown'] < -0.05), 'mkt_score'] += 3
df.loc[(df['mkt_drawdown'] >= -0.05) & (df['mkt_drawdown'] < -0.03), 'mkt_score'] += 1
df.loc[df['mkt_vol_5d'] > 0.015, 'mkt_score'] += 3
df.loc[(df['mkt_vol_5d'] > 0.01) & (df['mkt_vol_5d'] <= 0.015), 'mkt_score'] += 1
df.loc[df['consec_down_days'] >= 5, 'mkt_score'] += 3
df.loc[(df['consec_down_days'] >= 3) & (df['consec_down_days'] < 5), 'mkt_score'] += 2
df.loc[df['consec_down_days'] == 2, 'mkt_score'] += 1
df.loc[df['prev3_market_ret'] < -0.05, 'mkt_score'] += 3
df.loc[(df['prev3_market_ret'] >= -0.05) & (df['prev3_market_ret'] < -0.03), 'mkt_score'] += 2
df.loc[(df['prev3_market_ret'] >= -0.03) & (df['prev3_market_ret'] < -0.01), 'mkt_score'] += 1
df.loc[df['signals_today'] >= 11, 'mkt_score'] += 2
df.loc[(df['signals_today'] >= 8) & (df['signals_today'] < 11), 'mkt_score'] += 1
df.loc[df['weekday'].isin([1, 4]), 'mkt_score'] += 1
df.loc[df['had_signal_yesterday'] == 1, 'mkt_score'] += 1
df.loc[df['month'] == 7, 'mkt_score'] -= 2
df.loc[df['abs_gap'] > 0.15, 'mkt_score'] -= 1

# Stock score (NEW)
df['stk_score'] = 0
# Stock trend: down = good for LONG (capitulation), flat = good for SHORT (noise gap)
# LONG: stock down >5% = +3, down 2-5% = +2
df.loc[(df['direction']=='LONG') & (df['stock_ret_1sig'] < -0.05), 'stk_score'] += 3
df.loc[(df['direction']=='LONG') & (df['stock_ret_1sig'] >= -0.05) & (df['stock_ret_1sig'] < -0.02), 'stk_score'] += 2
# SHORT: stock flat (-2% to +2%) = +2 (pure noise gap)
df.loc[(df['direction']=='SHORT') & (df['stock_ret_1sig'] >= -0.02) & (df['stock_ret_1sig'] <= 0.02), 'stk_score'] += 2
# Stock drawdown: deep = good
df.loc[df['stock_drawdown'] < -0.15, 'stk_score'] += 2
df.loc[(df['stock_drawdown'] >= -0.15) & (df['stock_drawdown'] < -0.10), 'stk_score'] += 1
# Stock at new high = bad (gap is likely real breakout)
df.loc[df['stock_drawdown'] > 0, 'stk_score'] -= 2
# Signal frequency: 1-4 = good (repeat pattern), 6+ = bad (over-traded)
df.loc[(df['stock_signals_30d'] >= 1) & (df['stock_signals_30d'] <= 4), 'stk_score'] += 1
df.loc[df['stock_signals_30d'] >= 6, 'stk_score'] -= 2

# Combined score
df['total_score'] = df['mkt_score'] + df['stk_score']

def backtest(trades, pos_map, label):
    trades = trades.copy().sort_values('date')
    trades['pos_pct'] = 0.02
    for threshold, pct in sorted(pos_map, key=lambda x: x[0]):
        trades.loc[trades['total_score'] >= threshold, 'pos_pct'] = pct
    trades['ret'] = trades['pnl'] * trades['pos_pct']
    daily = trades.groupby(trades['date'].dt.date)['ret'].sum().sort_index()
    cap = 4_500_000; peak = cap; mdd = 0
    yearly_end = {}
    for date, ret in daily.items():
        cap *= (1 + ret)
        if cap > peak: peak = cap
        dd = (cap - peak) / peak
        if dd < mdd: mdd = dd
        yearly_end[date.year] = cap
    years = sorted(yearly_end.keys())
    n_years = len(years)
    cagr = ((cap / 4_500_000) ** (1/n_years) - 1) * 100
    prev = 4_500_000; worst_yr = 999
    yearly_rets = {}
    for yr in years:
        yr_ret = (yearly_end[yr] / prev - 1) * 100
        yearly_rets[yr] = yr_ret
        if yr_ret < worst_yr: worst_yr = yr_ret
        prev = yearly_end[yr]
    daily_rets = daily.values
    sharpe = np.mean(daily_rets) / np.std(daily_rets) * np.sqrt(252) if len(daily_rets) > 10 else 0
    print('  %-45s | CAGR=%6.1f%% MDD=%5.1f%% WorstYr=%+.1f%% Sharpe=%5.2f' % (label, cagr, mdd*100, worst_yr, sharpe))
    return cagr, mdd*100, worst_yr, sharpe, yearly_rets

print('='*80)
print('MODEL C: Market + Stock Factors Combined')
print('='*80)
print()

# Score distribution
print('Combined score distribution:')
for s in range(-5, 25):
    cnt = (df['total_score'] == s).sum()
    if cnt > 100:
        wr = df[df['total_score']==s]['win'].mean()*100
        pnl = df[df['total_score']==s]['pnl'].mean()*100
        print('  Score %2d: n=%5d WR=%.1f%% PnL=%+.3f%%' % (s, cnt, wr, pnl))
print()

# Test different position maps for combined score
pos_maps = [
    # Model B only (market score, max 12%)
    [(10, 0.12), (7, 0.09), (5, 0.07), (3, 0.05), (1, 0.04), (0, 0.02)],
    # Combined: higher thresholds since stock adds points
    [(13, 0.12), (10, 0.09), (7, 0.07), (4, 0.05), (2, 0.04), (0, 0.02)],
    [(14, 0.12), (11, 0.09), (8, 0.07), (5, 0.05), (2, 0.04), (0, 0.02)],
    [(15, 0.12), (12, 0.09), (9, 0.07), (6, 0.05), (3, 0.04), (0, 0.02)],
    [(12, 0.12), (9, 0.09), (6, 0.07), (3, 0.05), (1, 0.04), (0, 0.02)],
    # More aggressive
    [(13, 0.14), (10, 0.10), (7, 0.07), (4, 0.05), (2, 0.03), (0, 0.02)],
    [(15, 0.14), (12, 0.10), (9, 0.07), (6, 0.05), (3, 0.03), (0, 0.02)],
]

print('--- POSITION MAP TESTS (using combined score) ---')
best = (0, -99, -999, 0, None, None)
for i, pm in enumerate(pos_maps):
    c, m, w, s, yr = backtest(df, pm, 'CM%d' % i)
    if c > best[0] and m > -8:
        best = (c, m, w, s, pm, yr)

print()
print('--- COMPARE: Market-only vs Market+Stock ---')
# Market only (Model B PM4)
df['total_score'] = df['mkt_score']
backtest(df, [(10, 0.12), (7, 0.09), (5, 0.07), (3, 0.05), (1, 0.04), (0, 0.02)], 'Market only (Model B PM4)')

# Market + Stock
df['total_score'] = df['mkt_score'] + df['stk_score']
backtest(df, best[4], 'Market + Stock (best CM)')

print()
print('='*60)
print('BEST COMBINED: CAGR=%.1f%% MDD=%.1f%% WorstYr=%+.1f%% Sharpe=%.2f' % best[:4])
print('  pos_map: %s' % best[4])
print()
print('Yearly:')
for yr in sorted(best[5].keys()):
    print('  %d: %+7.1f%%' % (yr, best[5][yr]))
