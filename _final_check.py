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

# A group only (skip all at-limit)
group_a = df[~df['at_limit']].copy()

COST = 0.0017; SL = 0.06; TP = 0.04

def sim_normal(row):
    entry = row['entry']; d = row['direction']; hi = row['day_high']; lo = row['day_low']; cl = row['day_close']
    if d == 'SHORT':
        sl_p = entry*(1+SL); tp_p = entry*(1-TP)
        ep = sl_p if hi>=sl_p else (tp_p if lo<=tp_p else cl)
        return (entry-ep)/entry - 2*COST
    else:
        sl_p = entry*(1-SL); tp_p = entry*(1+TP)
        ep = sl_p if lo<=sl_p else (tp_p if hi>=tp_p else cl)
        return (ep-entry)/entry - 2*COST

group_a['pnl'] = group_a.apply(sim_normal, axis=1)
group_a['win'] = (group_a['pnl'] > 0).astype(int)
group_a['year'] = group_a['date'].dt.year
group_a['ret'] = group_a['pnl'] * 0.05  # 5% base position

# Compounding
group_a = group_a.sort_values('date')
daily = group_a.groupby(group_a['date'].dt.date)['ret'].sum().sort_index()
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

print('='*60)
print('FINAL STRATEGY: A GROUP ONLY (skip at-limit)')
print('='*60)
print('Total trades:', len(group_a))
print('WR: %.1f%%' % (group_a['win'].mean()*100))
print('Avg PnL: %+.3f%%' % (group_a['pnl'].mean()*100))
print('CAGR: %.1f%%' % cagr)
print('MDD: %.2f%%' % (mdd*100))
print('Final capital: %s' % format(int(cap), ','))
print()

print('Yearly:')
print('%-6s %8s %6s %9s %10s' % ('Year', 'Trades', 'WR%', 'AvgPnL%', 'YearRet%'))
print('-'*45)
prev_cap = 4_500_000
for yr in years:
    yr_trades = group_a[group_a['year']==yr]
    wr = yr_trades['win'].mean()*100
    avg_pnl = yr_trades['pnl'].mean()*100
    yr_ret = (yearly_end[yr] / prev_cap - 1) * 100
    print('%-6d %8d %5.1f%% %+8.3f%% %+9.1f%%' % (yr, len(yr_trades), wr, avg_pnl, yr_ret))
    prev_cap = yearly_end[yr]
