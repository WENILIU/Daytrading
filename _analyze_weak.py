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

# Compare weak years vs strong years
print("=== YEAR CHARACTERISTICS ===")
print(f"{'Year':<6} {'Trades':>6} {'WR%':>6} {'AvgGap%':>8} {'AvgPnL%':>8} {'MktRet%':>8} {'Stuck%':>7}")
print("-" * 60)
for year in sorted(df['year'].unique()):
    yr = df[df['year']==year]
    wr = yr['win'].mean()*100
    avg_gap = yr['abs_gap'].mean()*100
    avg_pnl = yr['pnl'].mean()*100
    mkt = yr['market_ret'].mean()*100
    stuck_pct = yr['stuck'].mean()*100
    marker = " <<<" if year in [2017, 2019] else ""
    print(f"{year:<6} {len(yr):>6} {wr:>5.1f}% {avg_gap:>7.2f}% {avg_pnl:>+7.3f}% {mkt:>+7.2f}% {stuck_pct:>6.1f}%{marker}")

print()

# What's different about 2017/2019?
weak = df[df['year'].isin([2017, 2019])]
strong = df[df['year'].isin([2020, 2021, 2024, 2025])]

print("=== WEAK (2017,2019) vs STRONG (2020,2021,2024,2025) ===")
print(f"{'Metric':<25} {'Weak':>10} {'Strong':>10} {'Diff':>10}")
print("-" * 55)
metrics = [
    ('Avg gap size', 'abs_gap', lambda x: x.mean()*100),
    ('Win rate', 'win', lambda x: x.mean()*100),
    ('Avg PnL', 'pnl', lambda x: x.mean()*100),
    ('Market return', 'market_ret', lambda x: x.mean()*100),
    ('Stuck rate', 'stuck', lambda x: x.mean()*100),
]
for label, col, fn in metrics:
    w = fn(weak[col]); s = fn(strong[col])
    print(f"{label:<25} {w:>+9.2f}% {s:>+9.2f}% {s-w:>+9.2f}%")

print()

# Gap size distribution
print("=== GAP SIZE vs WIN RATE (2017+2019) ===")
weak2 = df[df['year'].isin([2017, 2019])].copy()
bins = [0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.20]
labels = ['5-6%','6-7%','7-8%','8-9%','9-10%','>10%']
weak2['gap_bin'] = pd.cut(weak2['abs_gap'], bins=bins, labels=labels)
for b in labels:
    sub = weak2[weak2['gap_bin']==b]
    if len(sub)>0:
        wr = sub['win'].mean()*100
        pnl = sub['pnl'].mean()*100
        print(f"  {b:6s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")

print()
print("=== GAP SIZE vs WIN RATE (2020+2021+2024+2025) ===")
strong2 = df[df['year'].isin([2020, 2021, 2024, 2025])].copy()
strong2['gap_bin'] = pd.cut(strong2['abs_gap'], bins=bins, labels=labels)
for b in labels:
    sub = strong2[strong2['gap_bin']==b]
    if len(sub)>0:
        wr = sub['win'].mean()*100
        pnl = sub['pnl'].mean()*100
        print(f"  {b:6s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")

print()
# Market condition analysis for weak years
print("=== MARKET CONDITION (2017+2019) ===")
weak2['mkt'] = 'flat'
weak2.loc[weak2['market_ret'] > 0.02, 'mkt'] = 'up2'
weak2.loc[weak2['market_ret'] < -0.02, 'mkt'] = 'down2'
for cond in ['up2','flat','down2']:
    sub = weak2[weak2['mkt']==cond]
    if len(sub)>0:
        wr = sub['win'].mean()*100
        pnl = sub['pnl'].mean()*100
        print(f"  {cond:6s}: {len(sub):4d} ({len(sub)/len(weak2)*100:.0f}%) | WR={wr:5.1f}% | PnL={pnl:+.2f}%")
