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

# === MODEL C SCORE ===
df['score'] = 0
df.loc[df['mkt_drawdown'] < -0.10, 'score'] += 4
df.loc[(df['mkt_drawdown'] >= -0.10) & (df['mkt_drawdown'] < -0.05), 'score'] += 3
df.loc[(df['mkt_drawdown'] >= -0.05) & (df['mkt_drawdown'] < -0.03), 'score'] += 1
df.loc[df['mkt_vol_5d'] > 0.015, 'score'] += 3
df.loc[(df['mkt_vol_5d'] > 0.01) & (df['mkt_vol_5d'] <= 0.015), 'score'] += 1
df.loc[df['consec_down_days'] >= 5, 'score'] += 3
df.loc[(df['consec_down_days'] >= 3) & (df['consec_down_days'] < 5), 'score'] += 2
df.loc[df['consec_down_days'] == 2, 'score'] += 1
df.loc[df['prev3_market_ret'] < -0.05, 'score'] += 3
df.loc[(df['prev3_market_ret'] >= -0.05) & (df['prev3_market_ret'] < -0.03), 'score'] += 2
df.loc[(df['prev3_market_ret'] >= -0.03) & (df['prev3_market_ret'] < -0.01), 'score'] += 1
df.loc[df['signals_today'] >= 11, 'score'] += 2
df.loc[(df['signals_today'] >= 8) & (df['signals_today'] < 11), 'score'] += 1
df.loc[df['weekday'].isin([1, 4]), 'score'] += 1
df.loc[df['had_signal_yesterday'] == 1, 'score'] += 1
df.loc[df['month'] == 7, 'score'] -= 2
df.loc[df['abs_gap'] > 0.15, 'score'] -= 1
df.loc[(df['direction']=='LONG') & (df['stock_ret_1sig'] < -0.05), 'score'] += 3
df.loc[(df['direction']=='LONG') & (df['stock_ret_1sig'] >= -0.05) & (df['stock_ret_1sig'] < -0.02), 'score'] += 2
df.loc[(df['direction']=='SHORT') & (df['stock_ret_1sig'] >= -0.02) & (df['stock_ret_1sig'] <= 0.02), 'score'] += 2
df.loc[df['stock_drawdown'] < -0.15, 'score'] += 2
df.loc[(df['stock_drawdown'] >= -0.15) & (df['stock_drawdown'] < -0.10), 'score'] += 1
df.loc[df['stock_drawdown'] > 0, 'score'] -= 2
df.loc[(df['stock_signals_30d'] >= 1) & (df['stock_signals_30d'] <= 4), 'score'] += 1
df.loc[df['stock_signals_30d'] >= 6, 'score'] -= 2

# Position sizing
pos_map = [(10, 0.12), (7, 0.09), (5, 0.07), (3, 0.05), (1, 0.04), (0, 0.02)]
df['pos_pct'] = 0.02
for threshold, pct in sorted(pos_map, key=lambda x: x[0]):
    df.loc[df['score'] >= threshold, 'pos_pct'] = pct

# === REALISTIC BACKTEST: 450萬 + 整張 + 曝險上限 ===
CAPITAL = 4_500_000
MAX_EXPOSURE = 0.70  # 70% max daily exposure

df = df.sort_values(['date', 'score'], ascending=[True, False])  # Sort by date, then by score (best first)

# Simulate day by day
daily_results = {}
skipped_lot = 0
skipped_exposure = 0
total_trades = 0
total_skipped = 0

for date, day_group in df.groupby('date'):
    day_capital = CAPITAL  # Reset each day (positions are closed same day)
    day_exposure = 0
    day_ret = 0
    
    for _, sig in day_group.iterrows():
        entry_price = sig['entry']
        pos_value = CAPITAL * sig['pos_pct']
        
        # 整張 constraint
        shares = int(pos_value / entry_price / 1000) * 1000
        if shares < 1000:
            skipped_lot += 1
            total_skipped += 1
            continue
        
        actual_value = shares * entry_price
        
        # Exposure limit
        if day_exposure + actual_value > CAPITAL * MAX_EXPOSURE:
            skipped_exposure += 1
            total_skipped += 1
            continue
        
        day_exposure += actual_value
        # PnL in absolute terms
        trade_pnl = actual_value * sig['pnl']
        day_ret += trade_pnl / CAPITAL  # Normalize to capital
        total_trades += 1
    
    daily_results[date] = day_ret

# Compound
dates_sorted = sorted(daily_results.keys())
cap = CAPITAL
peak = cap
mdd = 0
yearly_end = {}
monthly_end = {}

for date in dates_sorted:
    ret = daily_results[date]
    cap *= (1 + ret)
    if cap > peak: peak = cap
    dd = (cap - peak) / peak
    if dd < mdd: mdd = dd
    yearly_end[date.year] = cap
    monthly_end[(date.year, date.month)] = cap

years = sorted(yearly_end.keys())
n_years = len(years)
cagr = ((cap / CAPITAL) ** (1/n_years) - 1) * 100

print('='*70)
print('MODEL C REALISTIC: 450萬 + 整張 + 70%%曝險上限')
print('='*70)
print('CAGR: %.1f%% | MDD: %.2f%% | Final: %s' % (cagr, mdd*100, format(int(cap), ',')))
print('Trades executed: %d | Skipped (lot): %d | Skipped (exposure): %d' % (total_trades, skipped_lot, skipped_exposure))
print('Skip rate: %.1f%%' % (total_skipped / (total_trades + total_skipped) * 100))
print()

# Yearly
print('--- YEARLY ---')
print('%-6s %10s %10s' % ('Year', 'YearRet%', 'EndCapital'))
print('-'*30)
prev_cap = CAPITAL
for yr in years:
    yr_ret = (yearly_end[yr] / prev_cap - 1) * 100
    print('%-6d %+9.1f%% %10s' % (yr, yr_ret, format(int(yearly_end[yr]), ',')))
    prev_cap = yearly_end[yr]

print()

# Monthly
print('--- MONTHLY (%) ---')
print('%-6s' % 'Year', end='')
for m in range(1, 13):
    print('%7s' % str(m), end='')
print('%9s' % 'Year')
print('-' * 100)

prev_cap = CAPITAL
for yr in years:
    print('%-6d' % yr, end='')
    yr_start = prev_cap
    for m in range(1, 13):
        key = (yr, m)
        if key in monthly_end:
            if m == 1:
                m_start = yr_start
            else:
                m_start = monthly_end.get((yr, m-1), yr_start)
            m_ret = (monthly_end[key] / m_start - 1) * 100
            print('%+6.1f%%' % m_ret, end='')
        else:
            print('      --', end='')
    yr_ret = (yearly_end[yr] / yr_start - 1) * 100
    print('%+8.1f%%' % yr_ret)
    prev_cap = yearly_end[yr]

# Compare with theoretical
print()
print('--- COMPARISON: Theoretical vs Realistic ---')
print('Theoretical (no constraints): CAGR=208.0%, MDD=-6.9%')
print('Realistic (450W + lot + 70%%): CAGR=%.1f%%, MDD=%.1f%%' % (cagr, mdd*100))
print('Difference: %+.1f%% CAGR' % (cagr - 208.0))
