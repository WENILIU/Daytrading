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

# Market breadth
daily_short = df[df['direction']=='SHORT'].groupby('date').size().rename('n_short')
daily_long = df[df['direction']=='LONG'].groupby('date').size().rename('n_long')
df = df.merge(daily_short, on='date', how='left').merge(daily_long, on='date', how='left')
df['n_short'] = df['n_short'].fillna(0).astype(int)
df['n_long'] = df['n_long'].fillna(0).astype(int)

# Gap rank
df['gap_rank'] = df.groupby('date')['abs_gap'].rank(ascending=False)

# === STOCK FEATURES ===
df = df.sort_values(['stock', 'date']).reset_index(drop=True)
df['prev_signal_close'] = df.groupby('stock')['prev_close'].shift(1)
df['stock_ret_1sig'] = (df['prev_close'] - df['prev_signal_close']) / df['prev_signal_close']
df['stock_high_5'] = df.groupby('stock')['prev_close'].transform(lambda x: x.rolling(5, min_periods=2).max())
df['stock_drawdown'] = (df['prev_close'] - df['stock_high_5']) / df['stock_high_5']

# Signal frequency 30d
df['stock_signals_30d'] = 0
for stock, grp in df.groupby('stock'):
    dates = grp['date'].values
    indices = grp.index.values
    for i in range(len(dates)):
        cutoff = dates[i] - np.timedelta64(30, 'D')
        count = np.sum(dates[:i] >= cutoff)
        df.at[indices[i], 'stock_signals_30d'] = count

df['prev_signal_date'] = df.groupby('stock')['date'].shift(1)
df['had_signal_yesterday'] = ((df['date'] - df['prev_signal_date']).dt.days == 1).astype(int)

# Distance to limit
df['gap_to_limit'] = np.where(df['direction']=='SHORT',
    (df['zhangting'] - df['entry']) / df['entry'],
    (df['entry'] - df['dieding']) / df['entry'])

# === BUILD FINAL SCORE ===
# Layer 1: Market regime (same as before)
df['s_mkt'] = 0
df.loc[df['mkt_drawdown'] < -0.10, 's_mkt'] += 4
df.loc[(df['mkt_drawdown'] >= -0.10) & (df['mkt_drawdown'] < -0.05), 's_mkt'] += 3
df.loc[(df['mkt_drawdown'] >= -0.05) & (df['mkt_drawdown'] < -0.03), 's_mkt'] += 1
df.loc[df['mkt_vol_5d'] > 0.015, 's_mkt'] += 3
df.loc[(df['mkt_vol_5d'] > 0.01) & (df['mkt_vol_5d'] <= 0.015), 's_mkt'] += 1
df.loc[df['consec_down_days'] >= 5, 's_mkt'] += 3
df.loc[(df['consec_down_days'] >= 3) & (df['consec_down_days'] < 5), 's_mkt'] += 2
df.loc[df['consec_down_days'] == 2, 's_mkt'] += 1
df.loc[df['prev3_market_ret'] < -0.05, 's_mkt'] += 3
df.loc[(df['prev3_market_ret'] >= -0.05) & (df['prev3_market_ret'] < -0.03), 's_mkt'] += 2
df.loc[(df['prev3_market_ret'] >= -0.03) & (df['prev3_market_ret'] < -0.01), 's_mkt'] += 1
df.loc[df['signals_today'] >= 11, 's_mkt'] += 2
df.loc[(df['signals_today'] >= 8) & (df['signals_today'] < 11), 's_mkt'] += 1
df.loc[df['weekday'].isin([1, 4]), 's_mkt'] += 1
df.loc[df['had_signal_yesterday'] == 1, 's_mkt'] += 1
df.loc[df['month'] == 7, 's_mkt'] -= 2
df.loc[df['abs_gap'] > 0.15, 's_mkt'] -= 1

# Layer 2: Stock-level
df['s_stk'] = 0
df.loc[(df['direction']=='LONG') & (df['stock_ret_1sig'] < -0.05), 's_stk'] += 3
df.loc[(df['direction']=='LONG') & (df['stock_ret_1sig'] >= -0.05) & (df['stock_ret_1sig'] < -0.02), 's_stk'] += 2
df.loc[(df['direction']=='SHORT') & (df['stock_ret_1sig'] >= -0.02) & (df['stock_ret_1sig'] <= 0.02), 's_stk'] += 2
df.loc[df['stock_drawdown'] < -0.15, 's_stk'] += 2
df.loc[(df['stock_drawdown'] >= -0.15) & (df['stock_drawdown'] < -0.10), 's_stk'] += 1
df.loc[df['stock_drawdown'] > 0, 's_stk'] -= 2
df.loc[(df['stock_signals_30d'] >= 1) & (df['stock_signals_30d'] <= 4), 's_stk'] += 1
df.loc[df['stock_signals_30d'] >= 6, 's_stk'] -= 2

# Layer 3: Signal quality (NEW)
df['s_sig'] = 0
# Gap rank: later rank (smaller gap) = better (pure noise, not news)
df.loc[df['gap_rank'] >= 15, 's_sig'] += 2
df.loc[(df['gap_rank'] >= 10) & (df['gap_rank'] < 15), 's_sig'] += 1
# Market breadth: LONG-heavy = capitulation = best for LONG
df.loc[(df['direction']=='LONG') & (df['n_long'] > df['n_short'] * 2), 's_sig'] += 2
df.loc[(df['direction']=='LONG') & (df['n_long'] > df['n_short']), 's_sig'] += 1
# Close to limit = more extreme = better reversal
df.loc[df['gap_to_limit'] < 0.01, 's_sig'] += 2
df.loc[(df['gap_to_limit'] >= 0.01) & (df['gap_to_limit'] < 0.02), 's_sig'] += 1

# Total
df['total_score'] = df['s_mkt'] + df['s_stk'] + df['s_sig']

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
    print('  %-50s | CAGR=%6.1f%% MDD=%5.1f%% WorstYr=%+.1f%% Sharpe=%5.2f' % (label, cagr, mdd*100, worst_yr, sharpe))
    return cagr, mdd*100, worst_yr, sharpe, yearly_rets

print('='*80)
print('FINAL MODEL: Market + Stock + Signal Quality')
print('='*80)
print()

# Score distribution
print('Score distribution (key levels):')
for s in [0, 3, 5, 8, 10, 12, 15, 18, 20, 22, 25]:
    sub = df[df['total_score'] >= s]
    if len(sub) > 50:
        print('  Score >= %2d: n=%5d WR=%.1f%% PnL=%+.3f%%' % (s, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100))
print()

# Test position maps
pos_maps = [
    [(15, 0.12), (12, 0.09), (9, 0.07), (6, 0.05), (3, 0.04), (0, 0.02)],
    [(14, 0.12), (11, 0.09), (8, 0.07), (5, 0.05), (2, 0.04), (0, 0.02)],
    [(13, 0.12), (10, 0.09), (7, 0.07), (4, 0.05), (2, 0.04), (0, 0.02)],
    [(12, 0.12), (9, 0.09), (6, 0.07), (3, 0.05), (1, 0.04), (0, 0.02)],
    [(16, 0.12), (13, 0.09), (10, 0.07), (7, 0.05), (4, 0.04), (0, 0.02)],
    [(15, 0.14), (12, 0.10), (9, 0.07), (6, 0.05), (3, 0.03), (0, 0.02)],
    [(14, 0.14), (11, 0.10), (8, 0.07), (5, 0.05), (2, 0.03), (0, 0.02)],
]

print('--- POSITION MAP TESTS ---')
best = (0, -99, -999, 0, None, None)
for i, pm in enumerate(pos_maps):
    c, m, w, s, yr = backtest(df, pm, 'FM%d' % i)
    if c > best[0] and m > -8:
        best = (c, m, w, s, pm, yr)

print()
print('--- COMPARISON ---')
# Market only (Model B PM4)
df['total_score'] = df['s_mkt']
backtest(df, [(10, 0.12), (7, 0.09), (5, 0.07), (3, 0.05), (1, 0.04), (0, 0.02)], 'Model B PM4 (market only)')

# Market + Stock (Model C)
df['total_score'] = df['s_mkt'] + df['s_stk']
backtest(df, [(10, 0.12), (7, 0.09), (5, 0.07), (3, 0.05), (1, 0.04), (0, 0.02)], 'Model C (market + stock)')

# Full (Model D)
df['total_score'] = df['s_mkt'] + df['s_stk'] + df['s_sig']
backtest(df, best[4], 'Model D (market + stock + signal quality)')

print()
print('='*60)
print('BEST FINAL: CAGR=%.1f%% MDD=%.1f%% WorstYr=%+.1f%% Sharpe=%.2f' % best[:4])
print('  pos_map: %s' % best[4])
print()
print('Yearly:')
for yr in sorted(best[5].keys()):
    print('  %d: %+7.1f%%' % (yr, best[5][yr]))
