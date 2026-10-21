"""
Test: 
A) Exclude stocks that open at 漲停/跌停
B) Wait for unlock: enter at 漲停-1tick, SL at 漲停 (re-lock = stop loss)
"""
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
    raw = pc * 1.10
    t = get_tick(pc)
    return int(raw / t) * t

def calc_dieding(pc):
    raw = pc * 0.90
    t = get_tick(pc)
    return int(raw / t) * t + t

df['zhangting'] = df['prev_close'].apply(calc_zhangting)
df['dieding'] = df['prev_close'].apply(calc_dieding)

COST = 0.0017; SL = 0.06; TP = 0.04

def sim_normal(row):
    """Standard simulation."""
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

def sim_unlock_short(row):
    """SHORT: enter at 漲停-1tick when unlocked. SL at 漲停 (re-lock)."""
    zt = row['zhangting']
    tick = get_tick(zt)
    entry = zt - tick  # enter just below 漲停
    sl_price = zt       # re-lock = stop loss
    tp_price = entry * (1 - TP)
    hi = row['day_high']; lo = row['day_low']; cl = row['day_close']
    
    # If day_close == 漲停: re-locked, SL hit
    if np.isclose(cl, zt, rtol=0.001):
        return (entry - sl_price) / entry - 2*COST  # small loss (1 tick)
    
    # If day_low <= TP: take profit
    if lo <= tp_price:
        return (entry - tp_price) / entry - 2*COST
    
    # Otherwise: close at day_close
    return (entry - cl) / entry - 2*COST

def sim_unlock_long(row):
    """LONG: enter at 跌停+1tick when unlocked. SL at 跌停 (re-lock)."""
    dd = row['dieding']
    tick = get_tick(dd)
    entry = dd + tick  # enter just above 跌停
    sl_price = dd       # re-lock = stop loss
    tp_price = entry * (1 + TP)
    hi = row['day_high']; lo = row['day_low']; cl = row['day_close']
    
    # If day_close == 跌停: re-locked, SL hit
    if np.isclose(cl, dd, rtol=0.001):
        return (sl_price - entry) / entry - 2*COST  # small loss
    
    # If day_high >= TP: take profit
    if hi >= tp_price:
        return (tp_price - entry) / entry - 2*COST
    
    # Otherwise: close at day_close
    return (cl - entry) / entry - 2*COST

# Classify signals
df['at_zhangting'] = (df['direction']=='SHORT') & np.isclose(df['entry'], df['zhangting'], rtol=0.002)
df['at_dieding'] = (df['direction']=='LONG') & np.isclose(df['entry'], df['dieding'], rtol=0.002)
df['at_limit'] = df['at_zhangting'] | df['at_dieding']

# A) Baseline (current strategy)
df['pnl_base'] = df.apply(sim_normal, axis=1)

# B) Exclude limit-open stocks
df['pnl_exclude'] = df.apply(lambda r: sim_normal(r) if not r['at_limit'] else 0, axis=1)
# Actually for exclude, we just don't trade them (pnl=0, no position)

# C) Unlock strategy: for limit-open stocks, use unlock simulation
def sim_with_unlock(row):
    if row['at_zhangting']:
        return sim_unlock_short(row)
    elif row['at_dieding']:
        return sim_unlock_long(row)
    else:
        return sim_normal(row)

df['pnl_unlock'] = df.apply(sim_with_unlock, axis=1)

# Compounding backtest
def compound(trades, pnl_col, label):
    trades = trades.copy()
    trades['ret'] = trades[pnl_col] * 0.05
    trades = trades[trades['ret'] != 0].sort_values('date')  # skip zero (excluded)
    daily = trades.groupby(trades['date'].dt.date)['ret'].sum().sort_index()
    cap = 4_500_000; peak = cap; mdd = 0
    yearly_cap = {}
    for date, ret in daily.items():
        cap *= (1 + ret)
        if cap > peak: peak = cap
        dd = (cap - peak) / peak
        if dd < mdd: mdd = dd
        yearly_cap[date.year] = cap
    years = len(set(d.year for d in daily.index))
    cagr = ((cap / 4_500_000) ** (1/max(years,1)) - 1) * 100
    
    print(f"\n{label}:")
    print(f"  CAGR: {cagr:.1f}% | MDD: {mdd*100:.2f}% | Final: {cap:,.0f}")
    print(f"  Trades: {len(trades)}")
    wr = (trades[pnl_col]>0).mean()*100
    avg = trades[pnl_col].mean()*100
    print(f"  WR: {wr:.1f}% | Avg PnL: {avg:+.2f}%")
    
    prev = 4_500_000
    for yr in sorted(yearly_cap.keys()):
        yr_ret = (yearly_cap[yr]/prev - 1)*100
        n = len(trades[trades['date'].dt.year==yr])
        print(f"  {yr}: {n:4d} trades, Return={yr_ret:+.1f}%")
        prev = yearly_cap[yr]
    return cagr, mdd

print("=" * 70)
print("COMPARISON: Limit-up/down handling")
print("=" * 70)
print(f"\nTotal signals: {len(df)}")
print(f"  At 漲停 (SHORT): {df['at_zhangting'].sum()}")
print(f"  At 跌停 (LONG):  {df['at_dieding'].sum()}")
print(f"  At limit total:  {df['at_limit'].sum()} ({df['at_limit'].mean()*100:.1f}%)")

compound(df, 'pnl_base', "A) BASELINE (current: enter at 漲停, force close 13:25)")
compound(df, 'pnl_exclude', "B) EXCLUDE limit-open (skip these trades entirely)")
compound(df, 'pnl_unlock', "C) UNLOCK strategy (wait for unlock, enter below 漲停)")

# Detail on C
print("\n=== C) Unlock strategy detail ===")
unlock_trades = df[df['at_limit']].copy()
unlock_trades['pnl'] = unlock_trades.apply(
    lambda r: sim_unlock_short(r) if r['at_zhangting'] else sim_unlock_long(r), axis=1)
print(f"Unlock trades: {len(unlock_trades)}")
print(f"  WR: {(unlock_trades['pnl']>0).mean()*100:.1f}%")
print(f"  Avg PnL: {unlock_trades['pnl'].mean()*100:+.2f}%")
print(f"  Total PnL: {unlock_trades['pnl'].sum()*100:.0f}%")

# Compare with baseline for same trades
baseline_limit = df[df['at_limit']].copy()
print(f"\nSame trades in baseline:")
print(f"  WR: {(baseline_limit['pnl_base']>0).mean()*100:.1f}%")
print(f"  Avg PnL: {baseline_limit['pnl_base'].mean()*100:+.2f}%")
print(f"  Total PnL: {baseline_limit['pnl_base'].sum()*100:.0f}%")
