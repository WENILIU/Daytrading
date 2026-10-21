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

daily_count = df.groupby('date').size().rename('signals_today')
df = df.merge(daily_count, on='date', how='left')

def full_backtest(trades, label):
    trades = trades.copy().sort_values('date')
    if len(trades) < 50:
        print('%s: too few (%d)' % (label, len(trades)))
        return
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
    
    prev = 4_500_000
    yearly_rets = {}
    for yr in years:
        yr_ret = (yearly_end[yr] / prev - 1) * 100
        yearly_rets[yr] = yr_ret
        prev = yearly_end[yr]
    
    worst_yr = min(yearly_rets.values())
    best_yr = max(yearly_rets.values())
    
    print()
    print('='*70)
    print('  %s' % label)
    print('='*70)
    print('  Trades: %d | WR: %.1f%% | AvgPnL: %+.3f%%' % (len(trades), trades['win'].mean()*100, trades['pnl'].mean()*100))
    print('  CAGR: %.1f%% | MDD: %.2f%% | WorstYr: %+.1f%% | BestYr: %+.1f%%' % (cagr, mdd*100, worst_yr, best_yr))
    print()
    print('  Yearly:')
    for yr in years:
        yr_trades = trades[trades['year']==yr]
        print('    %d: %+7.1f%% (n=%d, WR=%.1f%%)' % (yr, yearly_rets[yr], len(yr_trades), yr_trades['win'].mean()*100))

# === BASELINE ===
full_backtest(df, 'BASELINE: A group, fixed 5%')

# === FILTER 1: Prev day market |return| > 2% ===
mask1 = abs(df['prev_market_ret']) > 0.02
full_backtest(df[mask1], 'FILTER: |prev mkt return| > 2%')

# === FILTER 2: 11+ signals per day ===
mask2 = df['signals_today'] >= 11
full_backtest(df[mask2], 'FILTER: 11+ signals/day (high vol days)')

# === FILTER 3: Only Tue + Fri ===
mask3 = df['weekday'].isin([1, 4])
full_backtest(df[mask3], 'FILTER: Only Tuesday + Friday')

# === FILTER 4: Skip July ===
mask4 = df['month'] != 7
full_backtest(df[mask4], 'FILTER: Skip July')

# === FILTER 5: Skip gap > 15% ===
mask5 = df['abs_gap'] < 0.15
full_backtest(df[mask5], 'FILTER: Skip gap > 15%')

# === COMBO: Skip July + Skip gap>15% (minimal filter) ===
mask_combo = (df['month'] != 7) & (df['abs_gap'] < 0.15)
full_backtest(df[mask_combo], 'COMBO: Skip July + Skip gap>15%')
