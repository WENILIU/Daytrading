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
df['prev2_market_ret'] = df['date'].map((market_daily.shift(1) + market_daily.shift(2)))

daily_count = df.groupby('date').size().rename('signals_today')
df = df.merge(daily_count, on='date', how='left')

df = df.sort_values(['stock', 'date'])
df['prev_signal_date'] = df.groupby('stock')['date'].shift(1)
df['had_signal_yesterday'] = ((df['date'] - df['prev_signal_date']).dt.days == 1).astype(int)

def backtest_dynamic(trades, pos_func, label):
    trades = trades.copy().sort_values('date')
    trades['pos_pct'] = trades.apply(pos_func, axis=1)
    trades['ret'] = trades['pnl'] * trades['pos_pct']
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
    yearly_rets = {}
    for yr in years:
        yr_ret = (yearly_end[yr] / prev - 1) * 100
        yearly_rets[yr] = yr_ret
        if yr_ret < worst_yr: worst_yr = yr_ret
        prev = yearly_end[yr]
    print('  %-45s | CAGR=%6.1f%% MDD=%5.1f%% WorstYr=%+.1f%%' % (label, cagr, mdd*100, worst_yr))
    return cagr, mdd, yearly_rets

print('='*80)
print('DYNAMIC POSITION SIZING OPTIMIZATION')
print('='*80)
print()

# Baseline: fixed 5%
backtest_dynamic(df, lambda r: 0.05, 'Fixed 5% (baseline)')
print()

# Strategy 1: Kelly-like tiers based on signal quality
def tier_pos(row):
    score = 0
    # Day quality
    if row['weekday'] in [1, 4]: score += 1  # Tue/Fri
    # Market environment
    if row['prev_market_ret'] < -0.01: score += 2
    if row['prev_market_ret'] < -0.03: score += 1
    if row['prev_market_ret'] > 0.02: score += 1  # Extreme up also good
    # Volatility
    if row['signals_today'] >= 11: score += 2
    if row['signals_today'] >= 8: score += 1
    # Repeat
    if row['had_signal_yesterday']: score += 1
    # Penalties
    if row['month'] == 7: score -= 2
    if row['abs_gap'] > 0.15: score -= 1
    # Map score to position: -2 to +8 range
    # score <= -1: 3%, score 0-1: 4%, score 2-3: 5%, score 4-5: 6%, score 6+: 8%
    if score <= -1: return 0.03
    elif score <= 1: return 0.04
    elif score <= 3: return 0.05
    elif score <= 5: return 0.06
    else: return 0.08

backtest_dynamic(df, tier_pos, 'Tiered Kelly (3-8% based on signal quality)')

# Strategy 2: More aggressive
def tier_pos2(row):
    score = 0
    if row['weekday'] in [1, 4]: score += 1
    if row['prev_market_ret'] < -0.01: score += 2
    if row['prev_market_ret'] < -0.03: score += 2
    if row['prev_market_ret'] > 0.02: score += 1
    if row['signals_today'] >= 11: score += 2
    if row['signals_today'] >= 8: score += 1
    if row['had_signal_yesterday']: score += 1
    if row['month'] == 7: score -= 3
    if row['abs_gap'] > 0.15: score -= 1
    if score <= -2: return 0.02
    elif score <= 0: return 0.04
    elif score <= 2: return 0.05
    elif score <= 4: return 0.07
    else: return 0.10

backtest_dynamic(df, tier_pos2, 'Aggressive Kelly (2-10%)')

# Strategy 3: Only skip worst, boost best
def tier_pos3(row):
    # Skip July entirely (0%)
    if row['month'] == 7: return 0.0
    # Base
    base = 0.05
    # Boost on high-quality signals
    if row['signals_today'] >= 11 and row['prev_market_ret'] < -0.01:
        return 0.08
    if row['signals_today'] >= 11:
        return 0.07
    if row['prev_market_ret'] < -0.02:
        return 0.07
    if row['prev_market_ret'] < -0.01:
        return 0.06
    # Reduce on weak signals
    if row['weekday'] in [0, 2, 3] and abs(row['prev_market_ret']) < 0.005:
        return 0.03
    return base

backtest_dynamic(df, tier_pos3, 'Skip Jul + boost high-quality + reduce weak')

# Strategy 4: Market regime based
def tier_pos4(row):
    # Core insight: extreme market moves (either direction) = best gap fade
    # Flat market = worst
    mkt_abs = abs(row['prev_market_ret']) if not np.isnan(row['prev_market_ret']) else 0
    
    if row['month'] == 7: return 0.0
    
    if mkt_abs > 0.03: return 0.08  # Extreme: max size
    elif mkt_abs > 0.02: return 0.07
    elif mkt_abs > 0.01: return 0.06
    elif mkt_abs > 0.005: return 0.05
    else: return 0.03  # Flat market: minimum
    
backtest_dynamic(df, tier_pos4, 'Market volatility sizing (3-8%, skip Jul)')

# Strategy 5: Combined best
def tier_pos5(row):
    if row['month'] == 7: return 0.0
    
    score = 0
    # Market volatility is the #1 predictor
    mkt_abs = abs(row['prev_market_ret']) if not np.isnan(row['prev_market_ret']) else 0
    if mkt_abs > 0.03: score += 3
    elif mkt_abs > 0.02: score += 2
    elif mkt_abs > 0.01: score += 1
    
    # High signal count = high vol day
    if row['signals_today'] >= 11: score += 2
    elif row['signals_today'] >= 8: score += 1
    
    # Day of week
    if row['weekday'] in [1, 4]: score += 1
    
    # Repeat signal
    if row['had_signal_yesterday']: score += 1
    
    # Gap too large = risky
    if row['abs_gap'] > 0.15: score -= 2
    
    # Map to position
    if score >= 5: return 0.08
    elif score >= 3: return 0.06
    elif score >= 1: return 0.05
    else: return 0.03

backtest_dynamic(df, tier_pos5, 'Combined score (3-8%, skip Jul)')

print()
print('--- YEARLY DETAIL FOR BEST STRATEGY ---')
# Run the best one and show yearly
cagr5, mdd5, yearly5 = backtest_dynamic(df, tier_pos5, 'Best: Combined score')
print()
print('Yearly returns:')
for yr in sorted(yearly5.keys()):
    print('  %d: %+7.1f%%' % (yr, yearly5[yr]))
