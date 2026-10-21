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

# Classify
df['at_zhangting'] = (df['direction']=='SHORT') & np.isclose(df['entry'], df['zhangting'], rtol=0.002)
df['at_dieding'] = (df['direction']=='LONG') & np.isclose(df['entry'], df['dieding'], rtol=0.002)
df['at_limit'] = df['at_zhangting'] | df['at_dieding']
df['stuck_short'] = df['at_zhangting'] & np.isclose(df['day_close'], df['zhangting'], rtol=0.002)
df['stuck_long'] = df['at_dieding'] & np.isclose(df['day_close'], df['dieding'], rtol=0.002)
df['stuck'] = df['stuck_short'] | df['stuck_long']

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
        return sim_normal(row)

df['pnl'] = df.apply(sim_unlock, axis=1)
df['win'] = (df['pnl'] > 0).astype(int)
df['year'] = df['date'].dt.year
df['ret'] = df['pnl'] * 0.05

# Split groups
group_a = df[~df['at_limit']].copy()  # Normal gaps (not at limit)
group_b = df[df['at_limit']].copy()   # At limit (unlock strategy)

# For Group B: only the ones that actually unlock get traded
# Stuck ones = no trade (pnl=0, excluded)
group_b_traded = group_b[~group_b['stuck']].copy()  # Only unlocked ones
group_b_stuck = group_b[group_b['stuck']].copy()     # Never unlock = no trade

print("=" * 80)
print("GROUP A: Normal Gap (not at limit) - immediate entry")
print("=" * 80)
print(f"Signals: {len(group_a)} ({len(group_a)/len(df)*100:.1f}% of total)")
print(f"WR: {group_a['win'].mean()*100:.1f}% | Avg PnL: {group_a['pnl'].mean()*100:+.2f}%")
print()

print("=" * 80)
print("GROUP B: At Limit (unlock strategy)")
print("=" * 80)
print(f"Total at-limit signals: {len(group_b)} ({len(group_b)/len(df)*100:.1f}%)")
print(f"  Unlocked (traded): {len(group_b_traded)} ({len(group_b_traded)/len(group_b)*100:.1f}%)")
print(f"  Never unlocked (skip): {len(group_b_stuck)} ({len(group_b_stuck)/len(group_b)*100:.1f}%)")
print()
print(f"  Unlocked trades: WR={group_b_traded['win'].mean()*100:.1f}%, Avg PnL={group_b_traded['pnl'].mean()*100:+.2f}%")
print(f"  Skipped (stuck): no trade, PnL=0")
print()

# Yearly comparison
print(f"{'Year':<6} | {'A: Trades':>9} {'A: WR':>6} {'A: PnL':>8} {'A: Ret':>9} | {'B: Traded':>9} {'B: WR':>6} {'B: PnL':>8} {'B: Ret':>9} | {'B skip':>6}")
print("-" * 100)

# Compounding for each group separately
def yearly_ret(trades, label):
    trades = trades.copy().sort_values('date')
    if len(trades) == 0:
        return {}
    daily = trades.groupby(trades['date'].dt.date)['ret'].sum().sort_index()
    cap = 4_500_000
    yearly = {}
    for date, ret in daily.items():
        cap *= (1 + ret)
        yearly[date.year] = cap
    return yearly

yA = yearly_ret(group_a, 'A')
yB = yearly_ret(group_b_traded, 'B')

prevA = 4_500_000; prevB = 4_500_000
for year in sorted(df['year'].unique()):
    yr_a = group_a[group_a['year']==year]
    yr_b = group_b_traded[group_b_b['year']==year] if 'group_b_b' in dir() else group_b_traded[group_b_traded['year']==year]
    yr_b_all = group_b[group_b['year']==year]
    
    wrA = yr_a['win'].mean()*100 if len(yr_a)>0 else 0
    pnlA = yr_a['pnl'].mean()*100 if len(yr_a)>0 else 0
    wrB = yr_b['win'].mean()*100 if len(yr_b)>0 else 0
    pnlB = yr_b['pnl'].mean()*100 if len(yr_b)>0 else 0
    
    capA_y = yA.get(year, prevA)
    capB_y = yB.get(year, prevB)
    retA = (capA_y/prevA - 1)*100
    retB = (capB_y/prevB - 1)*100
    
    n_skip = len(yr_b_all) - len(yr_b)
    
    print(f"{year:<6} | {len(yr_a):>9} {wrA:>5.1f}% {pnlA:>+7.2f}% {retA:>+8.1f}% | {len(yr_b):>9} {wrB:>5.1f}% {pnlB:>+7.2f}% {retB:>+8.1f}% | {n_skip:>6}")
    prevA = capA_y; prevB = capB_y

# Totals
years = df['year'].nunique()
capA_final = max(yA.values()) if yA else 4_500_000
capB_final = max(yB.values()) if yB else 4_500_000
cagrA = ((capA_final/4_500_000)**(1/years)-1)*100
cagrB = ((capB_final/4_500_000)**(1/years)-1)*100
print("-" * 100)
print(f"{'TOTAL':<6} | {len(group_a):>9} {group_a['win'].mean()*100:>5.1f}% {group_a['pnl'].mean()*100:>+7.2f}% {cagrA:>+8.1f}% | {len(group_b_traded):>9} {group_b_traded['win'].mean()*100:>5.1f}% {group_b_traded['pnl'].mean()*100:>+7.2f}% {cagrB:>+8.1f}% | {len(group_b_stuck):>6}")
