import pandas as pd, numpy as np

df = pd.read_csv('first_bar_features.csv', parse_dates=['date'])
df = df[df['price_chg_1min'].notna()].copy()

COST = 0.0017; SL = 0.06; TP = 0.04

# Simulate with different entry times
def sim_with_entry(row, entry_col):
    entry = row[entry_col]
    if entry == 0 or pd.isna(entry): return np.nan
    d = row['direction']; hi = row.get('day_high', np.nan); lo = row.get('day_low', np.nan)
    # We don't have day_high/low in this file, use the signals pkl
    return None

# Load signals for day_high/low
sig = pd.read_pickle('gap_fade_signals_2010.pkl')
sig['date'] = pd.to_datetime(sig['date'])
sig['date_str'] = sig['date'].dt.strftime('%Y-%m-%d')

# Merge
merged = df.merge(
    sig[['date_str','stock','direction','day_high','day_low','day_close','entry']],
    on=['date_str','stock','direction'], how='left'
)
merged = merged[merged['day_high'].notna()].copy()
print(f"Merged: {len(merged)} trades")

# Simulate PnL with entry at different times
def sim_pnl(row, entry_val):
    if pd.isna(entry_val) or entry_val == 0: return np.nan
    d = row['direction']; hi = row['day_high']; lo = row['day_low']; cl = row['day_close']
    if d == 'SHORT':
        sl_p = entry_val*(1+SL); tp_p = entry_val*(1-TP)
        ep = sl_p if hi>=sl_p else (tp_p if lo<=tp_p else cl)
        return (entry_val-ep)/entry_val - 2*COST
    else:
        sl_p = entry_val*(1-SL); tp_p = entry_val*(1+TP)
        ep = sl_p if lo<=sl_p else (tp_p if hi>=tp_p else cl)
        return (ep-entry_val)/entry_val - 2*COST

# PnL at different entry times
merged['pnl_900'] = merged.apply(lambda r: sim_pnl(r, r['entry']), axis=1)
merged['pnl_901'] = merged.apply(lambda r: sim_pnl(r, r['entry_1min']), axis=1)
merged['pnl_902'] = merged.apply(lambda r: sim_pnl(r, r['entry_2min']), axis=1)
merged['pnl_903'] = merged.apply(lambda r: sim_pnl(r, r['entry_3min']), axis=1)

for col in ['pnl_900','pnl_901','pnl_902','pnl_903']:
    valid = merged[merged[col].notna()]
    wr = (valid[col]>0).mean()*100
    pnl = valid[col].mean()*100
    print(f"  Entry {col[-3:]}: {len(valid)} trades, WR={wr:.1f}%, avg PnL={pnl:+.2f}%")
print()

# Predictive power of first bar
short = merged[merged['direction']=='SHORT'].copy()
long_df = merged[merged['direction']=='LONG'].copy()

print("=== SHORT: First 1-min price direction ===")
short['win_900'] = (short['pnl_900']>0).astype(int)
bins = [-1,-0.02,-0.01,-0.005,0,0.005,0.01,0.02,1]
labels = ['<-2%','-2~-1%','-1~-0.5%','-0.5~0%','0~0.5%','0.5~1%','1~2%','>2%']
short['pc1'] = pd.cut(short['price_chg_1min'], bins=bins, labels=labels)
for b in labels:
    sub = short[short['pc1']==b]
    if len(sub)>5:
        wr = sub['win_900'].mean()*100
        pnl = sub['pnl_900'].mean()*100
        print(f"  {b:10s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")
print()

print("=== SHORT: First 1-min volume vs prev day ===")
bins_v = [0,0.005,0.01,0.02,0.05,0.1,0.2,100]
labels_v = ['<0.5%','0.5-1%','1-2%','2-5%','5-10%','10-20%','>20%']
short['v1r'] = pd.cut(short['vol_1min_vs_prev'], bins=bins_v, labels=labels_v)
for b in labels_v:
    sub = short[short['v1r']==b]
    if len(sub)>5:
        wr = sub['win_900'].mean()*100
        pnl = sub['pnl_900'].mean()*100
        print(f"  {b:8s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")
print()

print("=== SHORT: Bar 1 range (high-low / open) ===")
bins_r = [0,0.005,0.01,0.02,0.03,0.05,1]
labels_r = ['<0.5%','0.5-1%','1-2%','2-3%','3-5%','>5%']
short['rng'] = pd.cut(short['bar1_range'], bins=bins_r, labels=labels_r)
for b in labels_r:
    sub = short[short['rng']==b]
    if len(sub)>5:
        wr = sub['win_900'].mean()*100
        pnl = sub['pnl_900'].mean()*100
        print(f"  {b:8s}: {len(sub):4d} | WR={wr:5.1f}% | PnL={pnl:+.2f}%")
print()

# KEY TEST: Use 9:01 entry with first-bar filter
# If first bar shows price dropping (for SHORT), enter at 9:01 close
print("=== TEST: 9:01 entry + first bar filter ===")
# SHORT: enter at 9:01 only if first bar closed below open (price dropping)
short_take = short[(short['price_chg_1min'] < 0) & short['pnl_901'].notna()]
short_skip = short[(short['price_chg_1min'] >= 0) & short['pnl_900'].notna()]
print(f"  TAKE (bar1 down): {len(short_take)} trades, WR={(short_take['pnl_901']>0).mean()*100:.1f}%, PnL={short_take['pnl_901'].mean()*100:+.2f}%")
print(f"  SKIP (bar1 up):   {len(short_skip)} trades, WR={(short_skip['pnl_900']>0).mean()*100:.1f}%, PnL={short_skip['pnl_900'].mean()*100:+.2f}%")
print()

# Compare: enter all at 9:00 vs enter at 9:01 with filter
all_900 = merged[merged['pnl_900'].notna()]
print(f"  ALL at 9:00: {len(all_900)} trades, WR={(all_900['pnl_900']>0).mean()*100:.1f}%, PnL={all_900['pnl_900'].mean()*100:+.2f}%")
all_901_filtered = merged[
    ((merged['direction']=='SHORT') & (merged['price_chg_1min'] < 0) & merged['pnl_901'].notna()) |
    ((merged['direction']=='LONG') & (merged['price_chg_1min'] > 0) & merged['pnl_901'].notna())
]
print(f"  9:01 filtered: {len(all_901_filtered)} trades, WR={(all_901_filtered['pnl_901']>0).mean()*100:.1f}%, PnL={all_901_filtered['pnl_901'].mean()*100:+.2f}%")
print()

# What about: enter at 9:00, but use first bar to REJECT (exit at 9:01 if bad)?
# This is the "1-min stop loss" approach
print("=== TEST: Enter 9:00, EXIT at 9:01 if adverse >0.5% ===")
# SHORT: if bar1 close > entry * 1.005, exit at 9:01 price
merged['action_1min'] = 'hold'
merged.loc[(merged['direction']=='SHORT') & (merged['price_chg_1min'] > 0.005), 'action_1min'] = 'exit'
merged.loc[(merged['direction']=='LONG') & (merged['price_chg_1min'] < -0.005), 'action_1min'] = 'exit'

# For exit trades: PnL = (entry_900 - entry_901) / entry_900 for SHORT
merged['pnl_1min_stop'] = merged['pnl_900']  # default: normal
exit_mask = merged['action_1min'] == 'exit'
merged.loc[exit_mask & (merged['direction']=='SHORT'), 'pnl_1min_stop'] = (
    (merged.loc[exit_mask & (merged['direction']=='SHORT'), 'entry'] - 
     merged.loc[exit_mask & (merged['direction']=='SHORT'), 'entry_1min']) /
    merged.loc[exit_mask & (merged['direction']=='SHORT'), 'entry'] - 2*COST
)
merged.loc[exit_mask & (merged['direction']=='LONG'), 'pnl_1min_stop'] = (
    (merged.loc[exit_mask & (merged['direction']=='LONG'), 'entry_1min'] - 
     merged.loc[exit_mask & (merged['direction']=='LONG'), 'entry']) /
    merged.loc[exit_mask & (merged['direction']=='LONG'), 'entry'] - 2*COST
)

valid_stop = merged[merged['pnl_1min_stop'].notna()]
print(f"  With 1-min stop: {len(valid_stop)} trades, WR={(valid_stop['pnl_1min_stop']>0).mean()*100:.1f}%, PnL={valid_stop['pnl_1min_stop'].mean()*100:+.2f}%")
print(f"  Without:         {len(all_900)} trades, WR={(all_900['pnl_900']>0).mean()*100:.1f}%, PnL={all_900['pnl_900'].mean()*100:+.2f}%")
print()

# Compounding comparison
def compound(trades, pnl_col, label):
    trades = trades.copy()
    trades['date'] = pd.to_datetime(trades['date'])
    trades = trades[trades[pnl_col].notna()].sort_values('date')
    trades['ret'] = trades[pnl_col] * 0.05
    daily = trades.groupby(trades['date'].dt.date)['ret'].sum().sort_index()
    cap = 4_500_000; peak = cap; mdd = 0
    for date, ret in daily.items():
        cap *= (1 + ret)
        if cap > peak: peak = cap
        dd = (cap - peak) / peak
        if dd < mdd: mdd = dd
    years = len(set(d.year for d in daily.index))
    cagr = ((cap / 4_500_000) ** (1/max(years,1)) - 1) * 100
    print(f"  {label}: CAGR={cagr:.1f}%, MDD={mdd*100:.2f}%, Final={cap:,.0f}")

print("=== COMPOUNDING ===")
compound(merged, 'pnl_900', "A) Baseline (9:00 entry)")
compound(merged, 'pnl_1min_stop', "B) 9:00 entry + 1-min stop (exit if adverse>0.5%)")
