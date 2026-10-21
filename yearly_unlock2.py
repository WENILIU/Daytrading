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
COST = 0.0017; SL = 0.06; TP = 0.04

df['stuck_short'] = ((df['direction']=='SHORT') & np.isclose(df['entry'], df['zhangting'], rtol=0.002) & np.isclose(df['day_close'], df['zhangting'], rtol=0.002))
df['stuck_long'] = ((df['direction']=='LONG') & np.isclose(df['entry'], df['dieding'], rtol=0.002) & np.isclose(df['day_close'], df['dieding'], rtol=0.002))
df['stuck'] = df['stuck_short'] | df['stuck_long']

def sim_original(row):
    entry = row['entry']; d = row['direction']; hi = row['day_high']; lo = row['day_low']; cl = row['day_close']
    if d == 'SHORT':
        sl_p = entry*(1+SL); tp_p = entry*(1-TP)
        ep = sl_p if hi>=sl_p else (tp_p if lo<=tp_p else cl)
        return (entry-ep)/entry - 2*COST
    else:
        sl_p = entry*(1-SL); tp_p = entry*(1+TP)
        ep = sl_p if lo<=sl_p else (tp_p if hi>=tp_p else cl)
        return (ep-entry)/entry - 2*COST

def sim_unlock(row):
    if row['stuck_short']:
        zt = row['zhangting']; tick = get_tick(zt); entry = zt - tick; sl_price = zt; tp_price = entry*(1-TP)
        lo = row['day_low']; cl = row['day_close']
        if np.isclose(cl, zt, rtol=0.001): return (entry - sl_price)/entry - 2*COST
        elif lo <= tp_price: return (entry - tp_price)/entry - 2*COST
        else: return (entry - cl)/entry - 2*COST
    elif row['stuck_long']:
        dd = row['dieding']; tick = get_tick(dd); entry = dd + tick; sl_price = dd; tp_price = entry*(1+TP)
        hi = row['day_high']; cl = row['day_close']
        if np.isclose(cl, dd, rtol=0.001): return (sl_price - entry)/entry - 2*COST
        elif hi >= tp_price: return (tp_price - entry)/entry - 2*COST
        else: return (cl - entry)/entry - 2*COST
    else:
        return sim_original(row)

df['pnl'] = df.apply(sim_unlock, axis=1)
df['win'] = (df['pnl'] > 0).astype(int)
df['year'] = df['date'].dt.year
df['month'] = df['date'].dt.month
df['ret'] = df['pnl'] * 0.05

# Daily compounding for MDD
df_sorted = df.sort_values('date')
daily = df_sorted.groupby(df_sorted['date'].dt.date)['ret'].sum().sort_index()
cap = 4_500_000; peak = cap; mdd = 0
for date, ret in daily.items():
    cap *= (1 + ret)
    if cap > peak: peak = cap
    dd = (cap - peak) / peak
    if dd < mdd: mdd = dd

years = df['year'].nunique()
cagr = ((cap / 4_500_000) ** (1/years) - 1) * 100
print(f"CAGR: {cagr:.1f}% | MDD: {mdd*100:.2f}% | Final: {cap:,.0f}")
print(f"Total trades: {len(df)} | WR: {df['win'].mean()*100:.1f}%")
print()

# Monthly table
monthly_rets = {}
cap2 = 4_500_000
for year in sorted(df['year'].unique()):
    for month in range(1, 13):
        mask = (df['year'] == year) & (df['month'] == month)
        sub = df[mask]
        if len(sub) == 0:
            monthly_rets[(year, month)] = None
            continue
        daily_m = sub.groupby(sub['date'].dt.date)['ret'].sum().sort_index()
        m_start = cap2
        for date, ret in daily_m.items():
            cap2 *= (1 + ret)
        monthly_rets[(year, month)] = (cap2 / m_start - 1) * 100

print(f"{'Year':<6}", end='')
for m in range(1, 13):
    print(f"{m:>6}", end='')
print(f"{'Total':>8}")
print("-" * 92)
for year in sorted(df['year'].unique()):
    print(f"{year:<6}", end='')
    for m in range(1, 13):
        val = monthly_rets.get((year, m))
        if val is None:
            print(f"{'--':>6}", end='')
        else:
            print(f"{val:>+5.1f}", end='')
    yr_data = [d for d in [monthly_rets.get((year,m),0) or 0 for m in range(1,13)]]
    # Get actual year return
    yr_mask = df['year'] == year
    yr_daily = df[yr_mask].groupby(df[yr_mask]['date'].dt.date)['ret'].sum().sort_index()
    yr_cap_start = 4_500_000
    for y2 in range(2010, year):
        y2_mask = df['year'] == y2
        y2_daily = df[y2_mask].groupby(df[y2_mask]['date'].dt.date)['ret'].sum().sort_index()
        for _, r in y2_daily.items():
            yr_cap_start *= (1 + r)
    yr_cap_end = yr_cap_start
    for _, r in yr_daily.items():
        yr_cap_end *= (1 + r)
    yr_ret = (yr_cap_end / yr_cap_start - 1) * 100
    print(f"{yr_ret:>+7.1f}%")
