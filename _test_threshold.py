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
        entry = row['entry']; d = row['direction']; hi = row['day_high']; lo = row['day_low']; cl = row['day_close']
        if d == 'SHORT':
            sl_p = entry*(1+SL); tp_p = entry*(1-TP)
            ep = sl_p if hi>=sl_p else (tp_p if lo<=tp_p else cl)
            return (entry-ep)/entry - 2*COST
        else:
            sl_p = entry*(1-SL); tp_p = entry*(1+TP)
            ep = sl_p if lo<=sl_p else (tp_p if hi>=tp_p else cl)
            return (ep-entry)/entry - 2*COST

df['pnl'] = df.apply(sim_unlock, axis=1)
df['win'] = (df['pnl'] > 0).astype(int)
df['year'] = df['date'].dt.year
df['abs_gap'] = df['adj_gap'].abs()
df['ret'] = df['pnl'] * 0.05

def yearly_compound(trades, label):
    trades = trades.copy().sort_values('date')
    daily = trades.groupby(trades['date'].dt.date)['ret'].sum().sort_index()
    cap = 4_500_000; peak = cap; mdd = 0
    yearly = {}
    for date, ret in daily.items():
        cap *= (1 + ret)
        if cap > peak: peak = cap
        dd = (cap - peak) / peak
        if dd < mdd: mdd = dd
        yearly[date.year] = cap
    years_n = len(set(d.year for d in daily.index))
    cagr = ((cap / 4_500_000) ** (1/max(years_n,1)) - 1) * 100
    print(f"\n{label}: CAGR={cagr:.1f}% MDD={mdd*100:.2f}%")
    prev = 4_500_000
    weak_years = []
    for yr in sorted(yearly.keys()):
        yr_ret = (yearly[yr]/prev - 1)*100
        marker = " <<<" if yr_ret < 25 else ""
        if yr_ret < 25: weak_years.append(yr)
        print(f"  {yr}: {yr_ret:+.1f}%{marker}")
        prev = yearly[yr]
    return cagr, mdd, weak_years

# Test different gap thresholds
for threshold in [0.05, 0.06, 0.07]:
    filtered = df[df['abs_gap'] >= threshold].copy()
    yearly_compound(filtered, f"Gap >= {threshold*100:.0f}% ({len(filtered)} trades)")
    print()
