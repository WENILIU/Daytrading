"""
Test: reject ONLY negative-EV signals (keep all positive-EV ones).
The key: some signals have NEGATIVE expected value. Rejecting those is free money.
"""
import pandas as pd, numpy as np

df = pd.read_pickle('gap_fade_signals_2010.pkl')
df['date'] = pd.to_datetime(df['date'])

feat = pd.read_csv('volume_features.csv', parse_dates=['date'])
feat['vol5_vs_prev'] = feat['vol_first5'] / feat['vol_prev']
feat['date_str'] = feat['date'].dt.strftime('%Y-%m-%d')
df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')

merged = df.merge(
    feat[['date_str','stock','direction','price_chg_5min','vol5_vs_prev','vol_conc_5']],
    on=['date_str','stock','direction'], how='left'
)
has_data = merged[merged['price_chg_5min'].notna()].copy()

COST = 0.0017; SL = 0.06; TP = 0.04

def sim(row):
    entry = row['entry']; d = row['direction']
    hi = row['day_high']; lo = row['day_low']; cl = row['day_close']
    if d == 'SHORT':
        sl_p = entry*(1+SL); tp_p = entry*(1-TP)
        ep = sl_p if hi>=sl_p else (tp_p if lo<=tp_p else cl)
        return (entry-ep)/entry - 2*COST
    else:
        sl_p = entry*(1-SL); tp_p = entry*(1+TP)
        ep = sl_p if lo<=sl_p else (tp_p if hi>=tp_p else cl)
        return (ep-entry)/entry - 2*COST

has_data['pnl'] = has_data.apply(sim, axis=1)
has_data['win'] = (has_data['pnl'] > 0).astype(int)
has_data['year'] = has_data['date'].dt.year

print(f"Base: {len(has_data)} trades, WR={has_data['win'].mean()*100:.1f}%, PnL={has_data['pnl'].mean()*100:+.2f}%")
print()

# Find NEGATIVE EV subsets (real-time detectable)
print("=== NEGATIVE EV subsets (reject these = free money) ===")
print()

# For SHORT: price rising >2% + vol5/prev > 30%
short = has_data[has_data['direction']=='SHORT']
bad_short = short[(short['price_chg_5min'] > 0.02) & (short['vol5_vs_prev'] > 0.3)]
print(f"SHORT bad (rise>2% + vol5/prev>30%): {len(bad_short)} trades, WR={bad_short['win'].mean()*100:.1f}%, PnL={bad_short['pnl'].mean()*100:+.2f}%")

# For SHORT: price rising >1% + vol5/prev > 20%
bad_short2 = short[(short['price_chg_5min'] > 0.01) & (short['vol5_vs_prev'] > 0.2)]
print(f"SHORT bad (rise>1% + vol5/prev>20%): {len(bad_short2)} trades, WR={bad_short2['win'].mean()*100:.1f}%, PnL={bad_short2['pnl'].mean()*100:+.2f}%")

# For SHORT: price rising >1% (any volume)
bad_short3 = short[short['price_chg_5min'] > 0.01]
print(f"SHORT bad (rise>1%, any vol):        {len(bad_short3)} trades, WR={bad_short3['win'].mean()*100:.1f}%, PnL={bad_short3['pnl'].mean()*100:+.2f}%")

# For LONG: price dropping >1%
long_df = has_data[has_data['direction']=='LONG']
bad_long = long_df[long_df['price_chg_5min'] < -0.01]
print(f"LONG bad (drop>1%):                  {len(bad_long)} trades, WR={bad_long['win'].mean()*100:.1f}%, PnL={bad_long['pnl'].mean()*100:+.2f}%")

# For LONG: price dropping >2%
bad_long2 = long_df[long_df['price_chg_5min'] < -0.02]
print(f"LONG bad (drop>2%):                  {len(bad_long2)} trades, WR={bad_long2['win'].mean()*100:.1f}%, PnL={bad_long2['pnl'].mean()*100:+.2f}%")
print()

# Test: reject only clearly negative-EV signals
print("=== TEST: Reject negative-EV only ===")

# Strategy: reject SHORT if price rising >1%, reject LONG if price dropping >1%
# These are the only cases with clearly negative EV
reject_mask = (
    ((has_data['direction']=='SHORT') & (has_data['price_chg_5min'] > 0.01)) |
    ((has_data['direction']=='LONG') & (has_data['price_chg_5min'] < -0.01))
)
kept = has_data[~reject_mask]
rejected = has_data[reject_mask]

print(f"Rejected: {len(rejected)} trades, WR={rejected['win'].mean()*100:.1f}%, PnL={rejected['pnl'].mean()*100:+.2f}%")
print(f"Kept:     {len(kept)} trades, WR={kept['win'].mean()*100:.1f}%, PnL={kept['pnl'].mean()*100:+.2f}%")
print()

# Compounding comparison
def compound(trades, label):
    trades = trades.copy().sort_values('date')
    daily = trades.groupby(trades['date'].dt.date).agg(
        day_ret=('pnl', lambda x: sum(xi * 0.05 for xi in x))
    ).sort_index()
    
    cap = 4_500_000; peak = cap; mdd = 0
    yearly_cap = {}
    for date, row in daily.iterrows():
        cap *= (1 + row['day_ret'])
        if cap > peak: peak = cap
        dd = (cap - peak) / peak
        if dd < mdd: mdd = dd
        yearly_cap[date.year] = cap
    
    years = len(set(d.year for d in daily.index))
    cagr = ((cap / 4_500_000) ** (1/max(years,1)) - 1) * 100
    print(f"\n{label}:")
    print(f"  CAGR: {cagr:.1f}% | MDD: {mdd*100:.2f}% | Final: {cap:,.0f}")
    
    prev = 4_500_000
    for yr in sorted(yearly_cap.keys()):
        yr_ret = (yearly_cap[yr]/prev - 1)*100
        n = len(trades[trades['year']==yr])
        wr = (trades[trades['year']==yr]['pnl']>0).mean()*100
        print(f"  {yr}: {n:4d} trades, WR={wr:.1f}%, Return={yr_ret:+.1f}%")
        prev = yearly_cap[yr]
    return cagr, mdd

print()
cagr_base, mdd_base = compound(has_data, "BASELINE (no filter)")
cagr_keep, mdd_keep = compound(kept, "REJECT negative-EV (SHORT rise>1%, LONG drop>1%)")

# Also try: reject only extreme cases
reject_extreme = (
    ((has_data['direction']=='SHORT') & (has_data['price_chg_5min'] > 0.02) & (has_data['vol5_vs_prev'] > 0.3)) |
    ((has_data['direction']=='LONG') & (has_data['price_chg_5min'] < -0.02))
)
kept_extreme = has_data[~reject_extreme]
print()
cagr_ext, mdd_ext = compound(kept_extreme, "REJECT extreme only (SHORT rise>2%+vol>30%, LONG drop>2%)")

# Position sizing approach: Kelly adjustment
print()
print("=== POSITION SIZING: Kelly adjustment based on confirmation ===")
# Confirmed signals get 7% position, unconfirmed get 3%
has_data['position_pct'] = 0.05  # default
has_data.loc[
    ((has_data['direction']=='SHORT') & (has_data['price_chg_5min'] < -0.005)),
    'position_pct'
] = 0.07
has_data.loc[
    ((has_data['direction']=='LONG') & (has_data['price_chg_5min'] > 0.01)),
    'position_pct'
] = 0.07
has_data.loc[
    ((has_data['direction']=='SHORT') & (has_data['price_chg_5min'] > 0.01)),
    'position_pct'
] = 0.03
has_data.loc[
    ((has_data['direction']=='LONG') & (has_data['price_chg_5min'] < -0.01)),
    'position_pct'
] = 0.03

# Weighted PnL
has_data['weighted_pnl'] = has_data['pnl'] * has_data['position_pct'] / 0.05  # normalize to compare

def compound_weighted(trades, label):
    trades = trades.copy().sort_values('date')
    daily = trades.groupby(trades['date'].dt.date).agg(
        day_ret=('pnl', lambda x: sum(xi * trades.loc[x.index, 'position_pct'] for xi in x))
    ).sort_index()
    
    cap = 4_500_000; peak = cap; mdd = 0
    yearly_cap = {}
    for date, row in daily.iterrows():
        cap *= (1 + row['day_ret'])
        if cap > peak: peak = cap
        dd = (cap - peak) / peak
        if dd < mdd: mdd = dd
        yearly_cap[date.year] = cap
    
    years = len(set(d.year for d in daily.index))
    cagr = ((cap / 4_500_000) ** (1/max(years,1)) - 1) * 100
    print(f"\n{label}:")
    print(f"  CAGR: {cagr:.1f}% | MDD: {mdd*100:.2f}% | Final: {cap:,.0f}")
    prev = 4_500_000
    for yr in sorted(yearly_cap.keys()):
        yr_ret = (yearly_cap[yr]/prev - 1)*100
        print(f"  {yr}: Return={yr_ret:+.1f}%")
        prev = yearly_cap[yr]

compound_weighted(has_data, "KELLY SIZING (confirmed=7%, default=5%, negative-EV=3%)")
