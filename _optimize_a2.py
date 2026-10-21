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

# Market features (no look-ahead)
market_daily = df.groupby('date')['market_ret'].first().sort_index()
df['prev_market_ret'] = df['date'].map(market_daily.shift(1))
df['prev2_market_ret'] = df['date'].map((market_daily.shift(1) + market_daily.shift(2)))

# Signal count per day
daily_count = df.groupby('date').size().rename('signals_today')
df = df.merge(daily_count, on='date', how='left')

# Repeat signal
df = df.sort_values(['stock', 'date'])
df['prev_signal_date'] = df.groupby('stock')['date'].shift(1)
df['had_signal_yesterday'] = ((df['date'] - df['prev_signal_date']).dt.days == 1).astype(int)

def backtest(trades, label):
    trades = trades.copy().sort_values('date')
    if len(trades) < 10:
        print('  %s: too few trades (%d)' % (label, len(trades)))
        return None
    trades['ret'] = trades['pnl'] * 0.05
    daily = trades.groupby(trades['date'].dt.date)['ret'].sum().sort_index()
    cap = 4_500_000
    peak = cap
    mdd = 0
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
    
    # Worst year
    prev = 4_500_000
    worst_yr = 999
    for yr in years:
        yr_ret = (yearly_end[yr] / prev - 1) * 100
        if yr_ret < worst_yr: worst_yr = yr_ret
        prev = yearly_end[yr]
    
    wr = trades['win'].mean() * 100
    avg_pnl = trades['pnl'].mean() * 100
    
    print('  %-40s | n=%5d WR=%5.1f%% PnL=%+.3f%% | CAGR=%6.1f%% MDD=%5.1f%% WorstYr=%+.1f%%' % (
        label, len(trades), wr, avg_pnl, cagr, mdd*100, worst_yr))
    return cagr

print('='*80)
print('OPTIMIZATION COMBINATIONS (no look-ahead bias)')
print('='*80)
print()

# Baseline
backtest(df, 'BASELINE (A group only)')
print()

# --- Individual filters ---
print('--- INDIVIDUAL FILTERS ---')

# 1. Skip Mon/Wed/Thu (only trade Tue/Fri)
backtest(df[df['weekday'].isin([1, 4])], 'Only Tue+Fri')

# 2. Skip July
backtest(df[df['month'] != 7], 'Skip July')

# 3. Skip gap > 15%
backtest(df[df['abs_gap'] < 0.15], 'Skip gap >15%')

# 4. Previous day market down (mean reversion stronger)
backtest(df[df['prev_market_ret'] < 0], 'Only when prev day market down')

# 5. Previous day market down >1%
backtest(df[df['prev_market_ret'] < -0.01], 'Only when prev day market down >1%')

# 6. 2-day market down >2%
backtest(df[df['prev2_market_ret'] < -0.02], 'Only when 2d market down >2%')

# 7. Extreme market moves (either direction >2%)
backtest(df[abs(df['prev_market_ret']) > 0.02], 'Only when |prev mkt| >2%')

# 8. 11+ signals per day (high volatility days)
backtest(df[df['signals_today'] >= 11], 'Only 11+ signals/day')

# 9. Had signal yesterday (repeat = stronger)
backtest(df[df['had_signal_yesterday'] == 1], 'Only repeat signals')

print()
print('--- COMBINATIONS ---')

# A: Tue/Fri + skip July
backtest(df[(df['weekday'].isin([1, 4])) & (df['month'] != 7)], 'Tue/Fri + skip Jul')

# B: Prev mkt down + skip July
backtest(df[(df['prev_market_ret'] < 0) & (df['month'] != 7)], 'Prev mkt down + skip Jul')

# C: Prev mkt down OR extreme up + skip July + skip gap>15%
mask_c = ((df['prev_market_ret'] < -0.01) | (df['prev_market_ret'] > 0.02)) & (df['month'] != 7) & (df['abs_gap'] < 0.15)
backtest(df[mask_c], 'Extreme prev mkt + skip Jul + gap<15%')

# D: 11+ signals OR prev mkt down >1%
mask_d = (df['signals_today'] >= 11) | (df['prev_market_ret'] < -0.01)
backtest(df[mask_d], '11+ signals OR prev mkt down >1%')

# E: Skip Mon/Wed/Thu + skip July + skip gap>15%
mask_e = df['weekday'].isin([1, 4]) & (df['month'] != 7) & (df['abs_gap'] < 0.15)
backtest(df[mask_e], 'Tue/Fri + skip Jul + gap<15%')

# F: 2d market down >1% OR 11+ signals (high vol days)
mask_f = (df['prev2_market_ret'] < -0.01) | (df['signals_today'] >= 11)
backtest(df[mask_f], '2d mkt down >1% OR 11+ signals')

# G: NOT (Mon/Wed/Thu AND flat market AND low signals)
# = keep if: Tue/Fri OR market moved OR many signals
mask_g = (df['weekday'].isin([1, 4])) | (abs(df['prev_market_ret']) > 0.005) | (df['signals_today'] >= 8)
backtest(df[mask_g], 'Tue/Fri OR mkt moved OR many signals')

# H: Skip only the worst conditions: Mon/Wed/Thu + flat market + July
mask_h = ~((~df['weekday'].isin([1, 4])) & (abs(df['prev_market_ret']) < 0.005) & (df['month'] == 7))
backtest(df[mask_h], 'Skip only worst: Mon/Wed/Thu + flat + Jul')

# I: Position sizing approach - keep all but weight by signal quality
# (simulate with variable position size)
print()
print('--- WEIGHTED POSITION SIZING (keep all trades, vary size) ---')

# Score each trade
df['score'] = 0
df.loc[df['weekday'].isin([1, 4]), 'score'] += 1  # Tue/Fri
df.loc[df['prev_market_ret'] < -0.01, 'score'] += 2  # Prev mkt down
df.loc[df['prev_market_ret'] < -0.03, 'score'] += 1  # Prev mkt down >3%
df.loc[df['signals_today'] >= 11, 'score'] += 1  # High vol day
df.loc[df['had_signal_yesterday'] == 1, 'score'] += 1  # Repeat
df.loc[df['month'] == 7, 'score'] -= 2  # July penalty
df.loc[~df['weekday'].isin([1, 4]) & (abs(df['prev_market_ret']) < 0.005), 'score'] -= 1  # Bad day + flat

# Simulate with variable position size based on score
def backtest_weighted(trades, label):
    trades = trades.copy().sort_values('date')
    # Position multiplier: score 0 = 3%, score 3+ = 7%
    trades['pos_mult'] = np.clip(0.03 + trades['score'] * 0.01, 0.02, 0.08)
    trades['ret'] = trades['pnl'] * trades['pos_mult']
    daily = trades.groupby(trades['date'].dt.date)['ret'].sum().sort_index()
    cap = 4_500_000
    peak = cap
    mdd = 0
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
    prev = 4_500_000
    worst_yr = 999
    for yr in years:
        yr_ret = (yearly_end[yr] / prev - 1) * 100
        if yr_ret < worst_yr: worst_yr = yr_ret
        prev = yearly_end[yr]
    print('  %-40s | n=%5d | CAGR=%6.1f%% MDD=%5.1f%% WorstYr=%+.1f%%' % (
        label, len(trades), cagr, mdd*100, worst_yr))

backtest_weighted(df, 'Score-weighted (2-8% per trade)')

# Compare with fixed 5%
backtest(df, 'Fixed 5% (baseline)')
