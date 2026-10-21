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
    yearly_rets = {}
    for yr in years:
        yr_ret = (yearly_end[yr] / prev - 1) * 100
        yearly_rets[yr] = yr_ret
        prev = yearly_end[yr]
    worst_yr = min(yearly_rets.values())
    print('  %-50s | CAGR=%6.1f%% MDD=%5.1f%% WorstYr=%+.1f%%' % (label, cagr, mdd*100, worst_yr))
    return cagr, mdd, yearly_rets

print('='*80)
print('OPTIMIZED SCORING MODELS')
print('='*80)
print()

# Baseline
backtest_dynamic(df, lambda r: 0.05, 'BASELINE: Fixed 5%')
print()

# === MODEL A: Previous best (Tiered Kelly) ===
def model_a(row):
    score = 0
    if row['weekday'] in [1, 4]: score += 1
    if row['prev_market_ret'] < -0.01: score += 2
    if row['prev_market_ret'] < -0.03: score += 1
    if row['prev_market_ret'] > 0.02: score += 1
    if row['signals_today'] >= 11: score += 2
    if row['signals_today'] >= 8: score += 1
    if row['had_signal_yesterday']: score += 1
    if row['month'] == 7: score -= 2
    if row['abs_gap'] > 0.15: score -= 1
    if score <= -1: return 0.03
    elif score <= 1: return 0.04
    elif score <= 3: return 0.05
    elif score <= 5: return 0.06
    else: return 0.08

backtest_dynamic(df, model_a, 'MODEL A: Previous Tiered Kelly')

# === MODEL B: Add market drawdown + vol + consec down ===
def model_b(row):
    score = 0
    # Market drawdown (strongest new factor)
    dd = row['mkt_drawdown'] if not np.isnan(row['mkt_drawdown']) else 0
    if dd < -0.10: score += 4
    elif dd < -0.05: score += 3
    elif dd < -0.03: score += 1
    
    # Market volatility
    vol = row['mkt_vol_5d'] if not np.isnan(row['mkt_vol_5d']) else 0
    if vol > 0.015: score += 3
    elif vol > 0.01: score += 1
    
    # Consecutive down days
    cd = row['consec_down_days'] if not np.isnan(row['consec_down_days']) else 0
    if cd >= 5: score += 3
    elif cd >= 3: score += 2
    elif cd >= 2: score += 1
    
    # 3-day market return
    r3 = row['prev3_market_ret'] if not np.isnan(row['prev3_market_ret']) else 0
    if r3 < -0.05: score += 3
    elif r3 < -0.03: score += 2
    elif r3 < -0.01: score += 1
    
    # Signals per day
    if row['signals_today'] >= 11: score += 2
    elif row['signals_today'] >= 8: score += 1
    
    # Day of week
    if row['weekday'] in [1, 4]: score += 1
    
    # Repeat signal
    if row['had_signal_yesterday']: score += 1
    
    # Penalties
    if row['month'] == 7: score -= 2
    if row['abs_gap'] > 0.15: score -= 1
    
    # Map to position (wider range: 2-10%)
    if score >= 10: return 0.10
    elif score >= 7: return 0.08
    elif score >= 5: return 0.06
    elif score >= 3: return 0.05
    elif score >= 1: return 0.04
    else: return 0.02

backtest_dynamic(df, model_b, 'MODEL B: Full factors (2-10%)')

# === MODEL C: Same as B but more conservative (3-8%) ===
def model_c(row):
    score = 0
    dd = row['mkt_drawdown'] if not np.isnan(row['mkt_drawdown']) else 0
    if dd < -0.10: score += 4
    elif dd < -0.05: score += 3
    elif dd < -0.03: score += 1
    
    vol = row['mkt_vol_5d'] if not np.isnan(row['mkt_vol_5d']) else 0
    if vol > 0.015: score += 3
    elif vol > 0.01: score += 1
    
    cd = row['consec_down_days'] if not np.isnan(row['consec_down_days']) else 0
    if cd >= 5: score += 3
    elif cd >= 3: score += 2
    elif cd >= 2: score += 1
    
    r3 = row['prev3_market_ret'] if not np.isnan(row['prev3_market_ret']) else 0
    if r3 < -0.05: score += 3
    elif r3 < -0.03: score += 2
    elif r3 < -0.01: score += 1
    
    if row['signals_today'] >= 11: score += 2
    elif row['signals_today'] >= 8: score += 1
    
    if row['weekday'] in [1, 4]: score += 1
    if row['had_signal_yesterday']: score += 1
    if row['month'] == 7: score -= 2
    if row['abs_gap'] > 0.15: score -= 1
    
    # Conservative mapping (3-8%)
    if score >= 8: return 0.08
    elif score >= 5: return 0.07
    elif score >= 3: return 0.06
    elif score >= 1: return 0.04
    else: return 0.03

backtest_dynamic(df, model_c, 'MODEL C: Full factors conservative (3-8%)')

# === MODEL D: Focus on drawdown + vol only (simpler) ===
def model_d(row):
    score = 0
    dd = row['mkt_drawdown'] if not np.isnan(row['mkt_drawdown']) else 0
    if dd < -0.10: score += 4
    elif dd < -0.05: score += 3
    elif dd < -0.03: score += 2
    elif dd < -0.01: score += 1
    
    vol = row['mkt_vol_5d'] if not np.isnan(row['mkt_vol_5d']) else 0
    if vol > 0.02: score += 3
    elif vol > 0.015: score += 2
    elif vol > 0.01: score += 1
    
    if row['signals_today'] >= 11: score += 2
    elif row['signals_today'] >= 8: score += 1
    
    if row['month'] == 7: score -= 2
    if row['abs_gap'] > 0.15: score -= 1
    
    if score >= 7: return 0.08
    elif score >= 5: return 0.07
    elif score >= 3: return 0.05
    elif score >= 1: return 0.04
    else: return 0.03

backtest_dynamic(df, model_d, 'MODEL D: Drawdown+Vol only (3-8%)')

# === MODEL E: Aggressive with drawdown focus ===
def model_e(row):
    score = 0
    dd = row['mkt_drawdown'] if not np.isnan(row['mkt_drawdown']) else 0
    if dd < -0.10: score += 5
    elif dd < -0.05: score += 3
    elif dd < -0.03: score += 2
    
    vol = row['mkt_vol_5d'] if not np.isnan(row['mkt_vol_5d']) else 0
    if vol > 0.015: score += 3
    elif vol > 0.01: score += 1
    
    cd = row['consec_down_days'] if not np.isnan(row['consec_down_days']) else 0
    if cd >= 3: score += 2
    
    r3 = row['prev3_market_ret'] if not np.isnan(row['prev3_market_ret']) else 0
    if r3 < -0.03: score += 2
    
    if row['signals_today'] >= 11: score += 2
    if row['weekday'] in [1, 4]: score += 1
    if row['had_signal_yesterday']: score += 1
    if row['month'] == 7: score -= 3
    if row['abs_gap'] > 0.15: score -= 2
    
    if score >= 10: return 0.10
    elif score >= 7: return 0.08
    elif score >= 5: return 0.06
    elif score >= 3: return 0.05
    elif score >= 1: return 0.04
    else: return 0.02

backtest_dynamic(df, model_e, 'MODEL E: Aggressive drawdown focus (2-10%)')

print()
print('--- YEARLY DETAIL FOR BEST MODEL ---')
# Find best and show yearly
results = []
for name, func in [('A', model_a), ('B', model_b), ('C', model_c), ('D', model_d), ('E', model_e)]:
    cagr, mdd, yearly = backtest_dynamic(df, func, '  Detail: Model %s' % name)
    results.append((name, cagr, mdd, yearly))

best = max(results, key=lambda x: x[1])
print()
print('BEST MODEL: %s (CAGR=%.1f%%, MDD=%.1f%%)' % (best[0], best[1], best[2]))
print('Yearly:')
for yr in sorted(best[3].keys()):
    print('  %d: %+7.1f%%' % (yr, best[3][yr]))
