import pandas as pd, numpy as np
from itertools import product

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

# Pre-compute all features
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

# Pre-compute score components as columns (vectorized for speed)
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
df.loc[df['month'] == 7, 'f_pen'] = -2
df.loc[df['abs_gap'] > 0.15, 'f_pen'] = -1

# Total score with configurable weights
def calc_backtest(weights, pos_map, label):
    df['score'] = (weights[0]*df['f_dd'] + weights[1]*df['f_vol'] + weights[2]*df['f_cd'] + 
                   weights[3]*df['f_r3'] + weights[4]*df['f_sig'] + weights[5]*df['f_dow'] + 
                   weights[6]*df['f_repeat'] + weights[7]*df['f_pen'])
    
    # Map score to position
    df['pos_pct'] = 0.02
    for threshold, pct in pos_map:
        df.loc[df['score'] >= threshold, 'pos_pct'] = pct
    
    trades = df.copy().sort_values('date')
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
    for yr in years:
        yr_ret = (yearly_end[yr] / prev - 1) * 100
        if yr_ret < worst_yr: worst_yr = yr_ret
        prev = yearly_end[yr]
    sharpe = 0
    daily_rets = daily.values
    if len(daily_rets) > 10:
        sharpe = np.mean(daily_rets) / np.std(daily_rets) * np.sqrt(252)
    return cagr, mdd*100, worst_yr, sharpe

# Current Model B
pos_map_b = [(10, 0.10), (7, 0.08), (5, 0.06), (3, 0.05), (1, 0.04), (0, 0.02)]
weights_b = [1, 1, 1, 1, 1, 1, 1, 1]

cagr, mdd, wy, sharpe = calc_backtest(weights_b, pos_map_b, 'Model B')
print('Model B (current): CAGR=%.1f%% MDD=%.1f%% WorstYr=%+.1f%% Sharpe=%.2f' % (cagr, mdd, wy, sharpe))
print()

# Grid search over key parameters
print('=== PARAMETER SWEEP ===')
print()

# Sweep: position mapping thresholds
best_result = (0, -99, -999, 0, None, None)

pos_maps = [
    # (thresholds, positions) pairs
    [(10, 0.10), (7, 0.08), (5, 0.06), (3, 0.05), (1, 0.04), (0, 0.02)],  # Model B
    [(10, 0.10), (7, 0.08), (5, 0.07), (3, 0.05), (1, 0.04), (0, 0.03)],  # Higher floor
    [(8, 0.10), (6, 0.08), (4, 0.06), (2, 0.05), (0, 0.03)],  # Lower thresholds
    [(12, 0.10), (9, 0.08), (6, 0.06), (3, 0.05), (1, 0.04), (0, 0.02)],  # Higher thresholds
    [(10, 0.12), (7, 0.09), (5, 0.07), (3, 0.05), (1, 0.04), (0, 0.02)],  # Max 12%
    [(10, 0.10), (7, 0.08), (5, 0.06), (3, 0.05), (0, 0.03)],  # No 4% tier
    [(8, 0.10), (5, 0.07), (3, 0.05), (1, 0.03), (0, 0.02)],  # Simpler 5-tier
    [(10, 0.10), (6, 0.07), (3, 0.05), (0, 0.03)],  # Simple 4-tier
]

for i, pm in enumerate(pos_maps):
    cagr, mdd, wy, sharpe = calc_backtest(weights_b, pm, 'PM%d' % i)
    desc = str(pm)
    print('PM%d: CAGR=%6.1f%% MDD=%5.1f%% WorstYr=%+.1f%% Sharpe=%5.2f | %s' % (i, cagr, mdd, wy, sharpe, desc))
    if cagr > best_result[0] and mdd > -8:
        best_result = (cagr, mdd, wy, sharpe, pm, weights_b)

print()

# Sweep: weight adjustments
print('--- Weight variations ---')
weight_variants = [
    [1,1,1,1,1,1,1,1],  # Equal (current)
    [2,1,1,1,1,1,1,1],  # DD 2x
    [1,2,1,1,1,1,1,1],  # Vol 2x
    [2,2,1,1,1,1,1,1],  # DD+Vol 2x
    [2,2,2,2,1,1,1,1],  # Market factors 2x
    [1,1,1,1,2,1,1,1],  # Signals 2x
    [2,2,2,2,2,1,1,1],  # All market+signals 2x
    [3,2,2,2,1,1,1,1],  # DD dominant
    [1,1,1,1,1,1,1,2],  # Penalty 2x
]

best_pm = best_result[4] if best_result[4] else pos_maps[0]
for i, w in enumerate(weight_variants):
    cagr, mdd, wy, sharpe = calc_backtest(w, best_pm, 'W%d' % i)
    print('W%d: CAGR=%6.1f%% MDD=%5.1f%% WorstYr=%+.1f%% Sharpe=%5.2f | weights=%s' % (i, cagr, mdd, wy, sharpe, w))
    if cagr > best_result[0] and mdd > -8:
        best_result = (cagr, mdd, wy, sharpe, best_pm, w)

print()
print('='*60)
print('BEST FOUND: CAGR=%.1f%% MDD=%.1f%% WorstYr=%+.1f%% Sharpe=%.2f' % best_result[:4])
print('  pos_map: %s' % best_result[4])
print('  weights: %s' % best_result[5])
