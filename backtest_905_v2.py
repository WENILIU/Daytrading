"""
Compare 3 approaches:
A) Original: enter at 9:00, hold to TP/SL/close
B) 9:05 entry: wait for confirmation, enter at 9:05 price
C) Conditional: enter at 9:00, EXIT at 9:05 if not confirmed (small loss)
"""
import pandas as pd, numpy as np

df = pd.read_pickle('gap_fade_signals_2010.pkl')
df['date'] = pd.to_datetime(df['date'])

feat = pd.read_csv('volume_features.csv', parse_dates=['date'])
feat['vol5_vs_prev'] = feat['vol_first5'] / feat['vol_prev']
feat['date_str'] = feat['date'].dt.strftime('%Y-%m-%d')
df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')

merged = df.merge(
    feat[['date_str','stock','direction','price_chg_5min','vol5_vs_prev']],
    on=['date_str','stock','direction'], how='left'
)
has_data = merged[merged['price_chg_5min'].notna()].copy()
has_data['entry_905'] = has_data['entry'] * (1 + has_data['price_chg_5min'])
has_data = has_data[has_data['entry_905'] > 0].copy()

COST = 0.0017
SL = 0.06
TP = 0.04

def sim_original(row):
    """A: Enter at open, hold normally."""
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

def sim_905_entry(row):
    """B: Enter at 9:05 price (only if confirmed)."""
    entry = row['entry_905']; d = row['direction']
    hi = row['day_high']; lo = row['day_low']; cl = row['day_close']
    if d == 'SHORT':
        sl_p = entry*(1+SL); tp_p = entry*(1-TP)
        ep = sl_p if hi>=sl_p else (tp_p if lo<=tp_p else cl)
        return (entry-ep)/entry - 2*COST
    else:
        sl_p = entry*(1-SL); tp_p = entry*(1+TP)
        ep = sl_p if lo<=sl_p else (tp_p if hi>=tp_p else cl)
        return (ep-entry)/entry - 2*COST

def sim_conditional(row):
    """C: Enter at 9:00. At 9:05, if NOT confirmed, exit at 9:05 price (small loss).
    If confirmed, hold normally."""
    entry = row['entry']; d = row['direction']
    hi = row['day_high']; lo = row['day_low']; cl = row['day_close']
    pc5 = row['price_chg_5min']
    entry_905 = row['entry_905']
    
    # Check confirmation
    if d == 'SHORT':
        confirmed = pc5 < -0.005 and row['vol5_vs_prev'] < 0.5
    else:
        confirmed = pc5 > 0.01 and row['vol5_vs_prev'] < 0.5
    
    if not confirmed:
        # Exit at 9:05 price immediately
        if d == 'SHORT':
            return (entry - entry_905) / entry - 2*COST
        else:
            return (entry_905 - entry) / entry - 2*COST
    else:
        # Hold normally (same as original)
        if d == 'SHORT':
            sl_p = entry*(1+SL); tp_p = entry*(1-TP)
            ep = sl_p if hi>=sl_p else (tp_p if lo<=tp_p else cl)
            return (entry-ep)/entry - 2*COST
        else:
            sl_p = entry*(1-SL); tp_p = entry*(1+TP)
            ep = sl_p if lo<=sl_p else (tp_p if hi>=tp_p else cl)
            return (ep-entry)/entry - 2*COST

has_data['pnl_A'] = has_data.apply(sim_original, axis=1)
has_data['pnl_B'] = has_data.apply(sim_905_entry, axis=1)
has_data['pnl_C'] = has_data.apply(sim_conditional, axis=1)

# For B, only count confirmed trades
def is_confirmed(row):
    if row['direction'] == 'SHORT':
        return row['price_chg_5min'] < -0.005 and row['vol5_vs_prev'] < 0.5
    else:
        return row['price_chg_5min'] > 0.01 and row['vol5_vs_prev'] < 0.5

has_data['confirmed'] = has_data.apply(is_confirmed, axis=1)

print("=" * 70)
print("THREE APPROACHES COMPARED")
print("=" * 70)
print()

# A: Original
a = has_data
print(f"A) ORIGINAL (9:00 entry, no filter):")
print(f"   {len(a)} trades, WR={( a['pnl_A']>0).mean()*100:.1f}%, avg PnL={a['pnl_A'].mean()*100:+.2f}%")
print()

# B: 9:05 entry (only confirmed)
b = has_data[has_data['confirmed']]
print(f"B) 9:05 ENTRY (confirmed only):")
print(f"   {len(b)} trades, WR={(b['pnl_B']>0).mean()*100:.1f}%, avg PnL={b['pnl_B'].mean()*100:+.2f}%")
print()

# C: Conditional (enter at 9:00, exit at 9:05 if not confirmed)
c = has_data
confirmed_c = c[c['confirmed']]
rejected_c = c[~c['confirmed']]
print(f"C) CONDITIONAL (enter 9:00, exit 9:05 if unconfirmed):")
print(f"   {len(c)} trades total")
print(f"   Confirmed ({len(confirmed_c)}): WR={(confirmed_c['pnl_C']>0).mean()*100:.1f}%, PnL={confirmed_c['pnl_C'].mean()*100:+.2f}%")
print(f"   Rejected  ({len(rejected_c)}): WR={(rejected_c['pnl_C']>0).mean()*100:.1f}%, PnL={rejected_c['pnl_C'].mean()*100:+.2f}%")
print(f"   Overall: WR={(c['pnl_C']>0).mean()*100:.1f}%, avg PnL={c['pnl_C'].mean()*100:+.2f}%")
print()

# Full compounding backtest
print("=" * 70)
print("COMPOUNDING BACKTEST (450M, 5% position per trade)")
print("=" * 70)

def compound_backtest(trades, pnl_col, label):
    trades = trades.copy()
    trades['year'] = trades['date'].dt.year
    trades = trades.sort_values('date')
    
    # Daily compounding
    daily = trades.groupby(trades['date'].dt.date).agg(
        day_ret=(pnl_col, lambda x: sum(xi * 0.05 for xi in x))
    ).sort_index()
    
    cap = 4_500_000
    peak = cap
    mdd = 0
    yearly = {}
    
    for date, row in daily.iterrows():
        cap *= (1 + row['day_ret'])
        if cap > peak: peak = cap
        dd = (cap - peak) / peak
        if dd < mdd: mdd = dd
        yr = date.year
        yearly[yr] = yearly.get(yr, 4_500_000) 
        yearly[yr] = cap  # track end-of-year capital
    
    years = len(set(d.year for d in daily.index))
    cagr = ((cap / 4_500_000) ** (1/max(years,1)) - 1) * 100
    
    print(f"\n{label}:")
    print(f"  Final capital: {cap:,.0f}")
    print(f"  CAGR: {cagr:.1f}%")
    print(f"  MDD: {mdd*100:.2f}%")
    
    # Yearly breakdown
    prev_cap = 4_500_000
    for yr in sorted(yearly.keys()):
        yr_ret = (yearly[yr] / prev_cap - 1) * 100
        n_trades = len(trades[trades['year']==yr])
        wr = (trades[trades['year']==yr][pnl_col] > 0).mean() * 100
        print(f"  {yr}: {n_trades:4d} trades, WR={wr:.1f}%, Return={yr_ret:+.1f}%")
        prev_cap = yearly[yr]
    
    return cap, cagr, mdd

cap_a, cagr_a, mdd_a = compound_backtest(has_data, 'pnl_A', "A) ORIGINAL")
cap_b, cagr_b, mdd_b = compound_backtest(b, 'pnl_B', "B) 9:05 ENTRY (confirmed only)")
cap_c, cagr_c, mdd_c = compound_backtest(has_data, 'pnl_C', "C) CONDITIONAL (enter 9:00, exit 9:05 if unconfirmed)")

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"{'Approach':<45} {'CAGR':>8} {'MDD':>8} {'Final Cap':>14}")
print("-" * 80)
print(f"{'A) Original (9:00, no filter)':<45} {cagr_a:>7.1f}% {mdd_a*100:>7.2f}% {cap_a:>14,.0f}")
print(f"{'B) 9:05 entry (confirmed only)':<45} {cagr_b:>7.1f}% {mdd_b*100:>7.2f}% {cap_b:>14,.0f}")
print(f"{'C) Conditional (enter 9:00, exit if unconfirmed)':<45} {cagr_c:>7.1f}% {mdd_c*100:>7.2f}% {cap_c:>14,.0f}")
