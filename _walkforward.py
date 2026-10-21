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

df = df.sort_values(['stock', 'date'])
df['prev_signal_date'] = df.groupby('stock')['date'].shift(1)
df['had_signal_yesterday'] = ((df['date'] - df['prev_signal_date']).dt.days == 1).astype(int)

# Pre-compute score components
df['f_dd'] = 0
df.loc[df['mkt_drawdown'] < -0.10, 'f_dd'] = 4
df.loc[(df['mkt_drawdown'] >= -0.10) & (df['mkt_drawdown'] < -0.05), 'f_dd'] = 3
df.loc[(df['mkt_drawdown'] >= -0.05) & (df['mkt_drawdown'] < -0.03), 'f_dd'] = 1

df['f_vol'] = 0
df.loc[df['mkt_vol_5d'] > 0.015, 'f_vol'] = 3
df.loc[(df['mkt_vol_5d'] > 0.01) & (df['mkt_vol_5d'] <= 0.015), 'f_vol'] = 1

df['f_cd'] = 0
df.loc[df['consec_down_days'] >= 5, 'f_cd'] = 3
df.loc[(df['consec_down_days'] >= 3) & (df['consec_down_days'] < 5), 'f_cd'] = 2
df.loc[df['consec_down_days'] == 2, 'f_cd'] = 1

df['f_r3'] = 0
df.loc[df['prev3_market_ret'] < -0.05, 'f_r3'] = 3
df.loc[(df['prev3_market_ret'] >= -0.05) & (df['prev3_market_ret'] < -0.03), 'f_r3'] = 2
df.loc[(df['prev3_market_ret'] >= -0.03) & (df['prev3_market_ret'] < -0.01), 'f_r3'] = 1

df['f_sig'] = 0
df.loc[df['signals_today'] >= 11, 'f_sig'] = 2
df.loc[(df['signals_today'] >= 8) & (df['signals_today'] < 11), 'f_sig'] = 1

df['f_dow'] = 0
df.loc[df['weekday'].isin([1, 4]), 'f_dow'] = 1

df['f_repeat'] = df['had_signal_yesterday']

df['f_pen'] = 0
df.loc[df['month'] == 7, 'f_pen'] -= 2
df.loc[df['abs_gap'] > 0.15, 'f_pen'] -= 1

# Score (fixed weights = 1)
df['score'] = df['f_dd'] + df['f_vol'] + df['f_cd'] + df['f_r3'] + df['f_sig'] + df['f_dow'] + df['f_repeat'] + df['f_pen']

def backtest_period(trades, pos_map):
    trades = trades.copy().sort_values('date')
    trades['pos_pct'] = 0.02
    for threshold, pct in sorted(pos_map, key=lambda x: x[0]):
        trades.loc[trades['score'] >= threshold, 'pos_pct'] = pct
    trades['ret'] = trades['pnl'] * trades['pos_pct']
    daily = trades.groupby(trades['date'].dt.date)['ret'].sum().sort_index()
    if len(daily) == 0:
        return 0, 0, 0
    cap = 1.0
    peak = 1.0
    mdd = 0
    for date, ret in daily.items():
        cap *= (1 + ret)
        if cap > peak: peak = cap
        dd = (cap - peak) / peak
        if dd < mdd: mdd = dd
    n_days = len(daily)
    n_years = n_days / 252
    cagr = (cap ** (1/n_years) - 1) * 100 if n_years > 0.1 else 0
    return cagr, mdd * 100, cap

# === WALK-FORWARD TEST ===
# Strategy: Compare fixed Model B (max 10%) vs PM4 (max 12%) on out-of-sample periods
# We do NOT re-optimize parameters on training data (that would be true WF).
# Instead, we verify that the SAME parameters work consistently across time.

print('='*70)
print('WALK-FORWARD VALIDATION')
print('='*70)
print()
print('Method: Apply FIXED parameters to sequential out-of-sample windows.')
print('If performance is consistent across all windows, it is NOT overfitting.')
print()

# Define test windows (each ~3 years)
windows = [
    (2010, 2012, "Window 1: 2010-2012"),
    (2013, 2015, "Window 2: 2013-2015"),
    (2016, 2018, "Window 3: 2016-2018"),
    (2019, 2021, "Window 4: 2019-2021"),
    (2022, 2024, "Window 5: 2022-2024"),
    (2025, 2026, "Window 6: 2025-2026"),
]

# Configurations to test
configs = {
    'Fixed 5% (baseline)': [(0, 0.05)],
    'Model B (max 10%)': [(10, 0.10), (7, 0.08), (5, 0.06), (3, 0.05), (1, 0.04), (0, 0.02)],
    'PM4 (max 12%)': [(10, 0.12), (7, 0.09), (5, 0.07), (3, 0.05), (1, 0.04), (0, 0.02)],
}

print('%-25s | %s' % ('Config', ' | '.join(['W%d CAGR/MDD' % (i+1) for i in range(len(windows))])))
print('-' * 110)

for name, pm in configs.items():
    results = []
    for start_yr, end_yr, label in windows:
        mask = (df['year'] >= start_yr) & (df['year'] <= end_yr)
        subset = df[mask]
        cagr, mdd, growth = backtest_period(subset, pm)
        results.append((cagr, mdd))
    
    line = '%-25s | ' % name
    for cagr, mdd in results:
        line += '%+6.1f%%/%+5.1f%% ' % (cagr, mdd)
    print(line)

print()
print()

# === TRUE WALK-FORWARD: Optimize on train, test on next period ===
print('='*70)
print('TRUE WALK-FORWARD: Optimize on train -> Test on next period')
print('='*70)
print()

# Parameter candidates to choose from during "training"
param_candidates = [
    ('Fixed 5%', [(0, 0.05)]),
    ('Model B 10%', [(10, 0.10), (7, 0.08), (5, 0.06), (3, 0.05), (1, 0.04), (0, 0.02)]),
    ('PM4 12%', [(10, 0.12), (7, 0.09), (5, 0.07), (3, 0.05), (1, 0.04), (0, 0.02)]),
    ('PM2 low', [(8, 0.10), (6, 0.08), (4, 0.06), (2, 0.05), (0, 0.03)]),
    ('PM5 no4%', [(10, 0.10), (7, 0.08), (5, 0.06), (3, 0.05), (0, 0.03)]),
    ('PM9 aggr', [(10, 0.10), (6, 0.07), (3, 0.05), (0, 0.03)]),
]

# Rolling WF: train on N years, test on next 3 years
wf_windows = [
    (2010, 2019, 2020, 2022, "Train 2010-2019 -> Test 2020-2022"),
    (2010, 2022, 2023, 2025, "Train 2010-2022 -> Test 2023-2025"),
    (2013, 2022, 2023, 2026, "Train 2013-2022 -> Test 2023-2026"),
]

for train_start, train_end, test_start, test_end, label in wf_windows:
    print(label)
    train_mask = (df['year'] >= train_start) & (df['year'] <= train_end)
    test_mask = (df['year'] >= test_start) & (df['year'] <= test_end)
    train_data = df[train_mask]
    test_data = df[test_mask]
    
    # Select best on training
    best_train_cagr = -999
    best_config = None
    for pname, pm in param_candidates:
        cagr, mdd, _ = backtest_period(train_data, pm)
        if cagr > best_train_cagr and mdd > -10:
            best_train_cagr = cagr
            best_config = (pname, pm)
    
    # Test on out-of-sample
    test_cagr, test_mdd, _ = backtest_period(test_data, best_config[1])
    
    # Also test fixed 5% and Model B for comparison
    fixed_cagr, fixed_mdd, _ = backtest_period(test_data, [(0, 0.05)])
    mb_cagr, mb_mdd, _ = backtest_period(test_data, configs['Model B (max 10%)'])
    pm4_cagr, pm4_mdd, _ = backtest_period(test_data, configs['PM4 (max 12%)'])
    
    print('  Selected on train: %s (train CAGR=%.1f%%)' % (best_config[0], best_train_cagr))
    print('  OUT-OF-SAMPLE RESULTS:')
    print('    Selected config:  CAGR=%+6.1f%% MDD=%+5.1f%%' % (test_cagr, test_mdd))
    print('    Fixed 5%%:         CAGR=%+6.1f%% MDD=%+5.1f%%' % (fixed_cagr, fixed_mdd))
    print('    Model B (10%%):    CAGR=%+6.1f%% MDD=%+5.1f%%' % (mb_cagr, mb_mdd))
    print('    PM4 (12%%):        CAGR=%+6.1f%% MDD=%+5.1f%%' % (pm4_cagr, pm4_mdd))
    print()

# === FINAL VERDICT ===
print('='*70)
print('CONCLUSION')
print('='*70)
print()
print('If PM4 (12%) outperforms Fixed 5% and Model B (10%) consistently')
print('across ALL out-of-sample windows, it is NOT overfitting.')
