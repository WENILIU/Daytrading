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
# Market
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
# Stock
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

df['ret'] = df['pnl'] * df['pos_pct']

# === BACKTEST ===
df = df.sort_values('date')
daily = df.groupby(df['date'].dt.date)['ret'].sum().sort_index()
cap = 4_500_000
peak = cap
mdd = 0
mdd_date = None
yearly_end = {}
monthly_end = {}

for date, ret in daily.items():
    cap *= (1 + ret)
    if cap > peak:
        peak = cap
    dd = (cap - peak) / peak
    if dd < mdd:
        mdd = dd
        mdd_date = date
    yearly_end[date.year] = cap
    monthly_end[(date.year, date.month)] = cap

years = sorted(yearly_end.keys())
n_years = len(years)
cagr = ((cap / 4_500_000) ** (1/n_years) - 1) * 100

print('='*70)
print('MODEL C COMPLETE PERFORMANCE REPORT')
print('='*70)
print('CAGR: %.1f%% | MDD: %.2f%% (on %s) | Final: %s' % (cagr, mdd*100, mdd_date, format(int(cap), ',')))
print('Trades: %d | WR: %.1f%% | Avg PnL: %+.3f%%' % (len(df), df['win'].mean()*100, df['pnl'].mean()*100))
print()

# === YEARLY ===
print('--- YEARLY PERFORMANCE ---')
print('%-6s %8s %6s %9s %10s %10s' % ('Year', 'Trades', 'WR%', 'AvgPnL%', 'YearRet%', 'EndCapital'))
print('-'*60)
prev_cap = 4_500_000
for yr in years:
    yr_trades = df[df['year']==yr]
    wr = yr_trades['win'].mean()*100
    avg_pnl = yr_trades['pnl'].mean()*100
    yr_ret = (yearly_end[yr] / prev_cap - 1) * 100
    print('%-6d %8d %5.1f%% %+8.3f%% %+9.1f%% %10s' % (yr, len(yr_trades), wr, avg_pnl, yr_ret, format(int(yearly_end[yr]), ',')))
    prev_cap = yearly_end[yr]

print()

# === MONTHLY ===
print('--- MONTHLY PERFORMANCE (%) ---')
months = list(range(1, 13))
print('%-6s' % 'Year', end='')
for m in months:
    print('%7s' % str(m), end='')
print('%9s' % 'Year')
print('-' * 100)

prev_cap = 4_500_000
for yr in years:
    print('%-6d' % yr, end='')
    yr_start_cap = prev_cap
    for m in months:
        key = (yr, m)
        if key in monthly_end:
            # Get month start cap
            if m == 1:
                month_start = yr_start_cap
            else:
                prev_key = (yr, m-1)
                month_start = monthly_end.get(prev_key, yr_start_cap)
            month_ret = (monthly_end[key] / month_start - 1) * 100
            print('%+6.1f%%' % month_ret, end='')
        else:
            print('      --', end='')
    yr_ret = (yearly_end[yr] / yr_start_cap - 1) * 100
    print('%+8.1f%%' % yr_ret)
    prev_cap = yearly_end[yr]

print()

# === MONTHLY DETAIL (trades + WR) ===
print('--- MONTHLY DETAIL ---')
print('%-8s %6s %6s %9s %9s' % ('Year-Mo', 'Trades', 'WR%', 'AvgPnL%', 'MonthRet%'))
print('-'*45)
prev_cap = 4_500_000
for yr in years:
    yr_start = prev_cap
    for m in range(1, 13):
        key = (yr, m)
        if key not in monthly_end:
            continue
        mask = (df['year']==yr) & (df['month']==m)
        sub = df[mask]
        if len(sub) == 0:
            continue
        if m == 1:
            m_start = yr_start
        else:
            m_start = monthly_end.get((yr, m-1), yr_start)
        m_ret = (monthly_end[key] / m_start - 1) * 100
        print('%d-%02d  %6d %5.1f%% %+8.3f%% %+8.1f%%' % (yr, m, len(sub), sub['win'].mean()*100, sub['pnl'].mean()*100, m_ret))
    prev_cap = yearly_end[yr]

# === ROLLING STATS ===
print()
print('--- ROLLING PERFORMANCE ---')
daily_series = pd.Series(daily.values, index=pd.to_datetime(daily.index))
for window, label in [(63, '3M'), (126, '6M'), (252, '12M')]:
    rolling = daily_series.rolling(window).apply(lambda x: (1+pd.Series(x)).prod().prod() - 1)
    rolling = rolling.dropna()
    neg = (rolling < 0).sum()
    worst = rolling.min() * 100
    total = len(rolling)
    print('  Rolling %s: %d periods, %d negative (%.1f%%), worst: %+.2f%%' % (label, total, neg, neg/total*100, worst*100))

# Monthly stats
monthly_rets = []
prev = 4_500_000
for yr in years:
    for m in range(1, 13):
        key = (yr, m)
        if key not in monthly_end:
            continue
        if m == 1:
            m_start = prev
        else:
            m_start = monthly_end.get((yr, m-1), prev)
        m_ret = (monthly_end[key] / m_start - 1)
        monthly_rets.append(m_ret)
    prev = yearly_end[yr]

mr = np.array(monthly_rets)
print()
print('  Monthly: %d months, %d positive (%.1f%%), avg: %+.2f%%, worst: %+.2f%%' % (
    len(mr), (mr>0).sum(), (mr>0).mean()*100, mr.mean()*100, mr.min()*100))
