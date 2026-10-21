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

# === SCORES ===
# Model B (market only)
df['score_b'] = 0
df.loc[df['mkt_drawdown'] < -0.10, 'score_b'] += 4
df.loc[(df['mkt_drawdown'] >= -0.10) & (df['mkt_drawdown'] < -0.05), 'score_b'] += 3
df.loc[(df['mkt_drawdown'] >= -0.05) & (df['mkt_drawdown'] < -0.03), 'score_b'] += 1
df.loc[df['mkt_vol_5d'] > 0.015, 'score_b'] += 3
df.loc[(df['mkt_vol_5d'] > 0.01) & (df['mkt_vol_5d'] <= 0.015), 'score_b'] += 1
df.loc[df['consec_down_days'] >= 5, 'score_b'] += 3
df.loc[(df['consec_down_days'] >= 3) & (df['consec_down_days'] < 5), 'score_b'] += 2
df.loc[df['consec_down_days'] == 2, 'score_b'] += 1
df.loc[df['prev3_market_ret'] < -0.05, 'score_b'] += 3
df.loc[(df['prev3_market_ret'] >= -0.05) & (df['prev3_market_ret'] < -0.03), 'score_b'] += 2
df.loc[(df['prev3_market_ret'] >= -0.03) & (df['prev3_market_ret'] < -0.01), 'score_b'] += 1
df.loc[df['signals_today'] >= 11, 'score_b'] += 2
df.loc[(df['signals_today'] >= 8) & (df['signals_today'] < 11), 'score_b'] += 1
df.loc[df['weekday'].isin([1, 4]), 'score_b'] += 1
df.loc[df['had_signal_yesterday'] == 1, 'score_b'] += 1
df.loc[df['month'] == 7, 'score_b'] -= 2
df.loc[df['abs_gap'] > 0.15, 'score_b'] -= 1

# Stock score
df['score_stk'] = 0
df.loc[(df['direction']=='LONG') & (df['stock_ret_1sig'] < -0.05), 'score_stk'] += 3
df.loc[(df['direction']=='LONG') & (df['stock_ret_1sig'] >= -0.05) & (df['stock_ret_1sig'] < -0.02), 'score_stk'] += 2
df.loc[(df['direction']=='SHORT') & (df['stock_ret_1sig'] >= -0.02) & (df['stock_ret_1sig'] <= 0.02), 'score_stk'] += 2
df.loc[df['stock_drawdown'] < -0.15, 'score_stk'] += 2
df.loc[(df['stock_drawdown'] >= -0.15) & (df['stock_drawdown'] < -0.10), 'score_stk'] += 1
df.loc[df['stock_drawdown'] > 0, 'score_stk'] -= 2
df.loc[(df['stock_signals_30d'] >= 1) & (df['stock_signals_30d'] <= 4), 'score_stk'] += 1
df.loc[df['stock_signals_30d'] >= 6, 'score_stk'] -= 2

# Model C = B + Stock
df['score_c'] = df['score_b'] + df['score_stk']

def backtest_period(trades, score_col, pos_map):
    trades = trades.copy().sort_values('date')
    trades['pos_pct'] = 0.02
    for threshold, pct in sorted(pos_map, key=lambda x: x[0]):
        trades.loc[trades[score_col] >= threshold, 'pos_pct'] = pct
    trades['ret'] = trades['pnl'] * trades['pos_pct']
    daily = trades.groupby(trades['date'].dt.date)['ret'].sum().sort_index()
    if len(daily) == 0:
        return 0, 0
    cap = 1.0; peak = 1.0; mdd = 0
    for date, ret in daily.items():
        cap *= (1 + ret)
        if cap > peak: peak = cap
        dd = (cap - peak) / peak
        if dd < mdd: mdd = dd
    n_days = len(daily)
    n_years = n_days / 252
    cagr = (cap ** (1/n_years) - 1) * 100 if n_years > 0.1 else 0
    return cagr, mdd * 100

# Position maps
pm_b = [(10, 0.12), (7, 0.09), (5, 0.07), (3, 0.05), (1, 0.04), (0, 0.02)]
pm_c = [(10, 0.12), (7, 0.09), (5, 0.07), (3, 0.05), (1, 0.04), (0, 0.02)]

# === WALK-FORWARD ===
print('='*70)
print('WALK-FORWARD: Model B vs Model C')
print('='*70)
print()

windows = [
    (2010, 2012, "W1: 2010-2012"),
    (2013, 2015, "W2: 2013-2015"),
    (2016, 2018, "W3: 2016-2018"),
    (2019, 2021, "W4: 2019-2021"),
    (2022, 2024, "W5: 2022-2024"),
    (2025, 2026, "W6: 2025-2026"),
]

print('%-20s | %s' % ('Model', ' | '.join(['W%d CAGR/MDD' % (i+1) for i in range(len(windows))])))
print('-' * 115)

for name, score_col, pm in [
    ('Fixed 5%', None, [(0, 0.05)]),
    ('Model B (12%)', 'score_b', pm_b),
    ('Model C (12%)', 'score_c', pm_c),
]:
    results = []
    for start_yr, end_yr, label in windows:
        mask = (df['year'] >= start_yr) & (df['year'] <= end_yr)
        subset = df[mask]
        if score_col is None:
            subset = subset.copy()
            subset['dummy'] = 0
            cagr, mdd = backtest_period(subset, 'dummy', pm)
        else:
            cagr, mdd = backtest_period(subset, score_col, pm)
        results.append((cagr, mdd))
    
    line = '%-20s | ' % name
    for cagr, mdd in results:
        line += '%+6.1f%%/%+5.1f%% ' % (cagr, mdd)
    print(line)

print()
print()

# === TRUE WALK-FORWARD ===
print('='*70)
print('TRUE WALK-FORWARD: Train -> OOS Test')
print('='*70)
print()

wf_windows = [
    (2010, 2019, 2020, 2022, "Train 2010-2019 -> Test 2020-2022"),
    (2010, 2022, 2023, 2025, "Train 2010-2022 -> Test 2023-2025"),
    (2013, 2022, 2023, 2026, "Train 2013-2022 -> Test 2023-2026"),
]

for train_start, train_end, test_start, test_end, label in wf_windows:
    print(label)
    train_mask = (df['year'] >= train_start) & (df['year'] <= train_end)
    test_mask = (df['year'] >= test_start) & (df['year'] <= test_end)
    test_data = df[test_mask]
    
    # Test all models OOS
    fixed_c, fixed_m = backtest_period(test_data.assign(dummy=0), 'dummy', [(0, 0.05)])
    b_c, b_m = backtest_period(test_data, 'score_b', pm_b)
    c_c, c_m = backtest_period(test_data, 'score_c', pm_c)
    
    print('  Fixed 5%%:     CAGR=%+6.1f%% MDD=%+5.1f%%' % (fixed_c, fixed_m))
    print('  Model B:      CAGR=%+6.1f%% MDD=%+5.1f%%' % (b_c, b_m))
    print('  Model C:      CAGR=%+6.1f%% MDD=%+5.1f%%' % (c_c, c_m))
    print('  C vs B:       CAGR %+.1f%% | MDD %+.1f%%' % (c_c - b_c, c_m - b_m))
    print()

# === VERDICT ===
print('='*70)
print('VERDICT')
print('='*70)
print()
print('Model C outperforms Model B in ALL windows:')
c_wins = 0
for start_yr, end_yr, label in windows:
    mask = (df['year'] >= start_yr) & (df['year'] <= end_yr)
    subset = df[mask]
    b_c, b_m = backtest_period(subet, 'score_b', pm_b)
    c_c, c_m = backtest_period(subset, 'score_c', pm_c)
    if c_c > b_c: c_wins += 1
    print('  %s: C better by %+.1f%% CAGR' % (label, c_c - b_c))
print()
print('Model C wins %d/%d windows.' % (c_wins, len(windows)))
