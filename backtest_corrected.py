"""
Corrected backtest: stuck trades get -5% PnL (next-day reality).
Compare with: exclude stuck, and unlock strategy.
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

# Identify stuck
df['stuck_short'] = ((df['direction']=='SHORT') & 
    np.isclose(df['entry'], df['zhangting'], rtol=0.002) & 
    np.isclose(df['day_close'], df['zhangting'], rtol=0.002))
df['stuck_long'] = ((df['direction']=='LONG') & 
    np.isclose(df['entry'], df['dieding'], rtol=0.002) & 
    np.isclose(df['day_close'], df['dieding'], rtol=0.002))
df['stuck'] = df['stuck_short'] | df['stuck_long']

# Measured next-day PnL for stuck trades
STUCK_SHORT_PNL = -0.0522  # -5.22% (measured from 603 samples)
STUCK_LONG_PNL = -0.0458   # -4.58% (measured from 290 samples)

def sim_corrected(row):
    """Corrected: stuck trades get actual next-day PnL."""
    if row['stuck_short']:
        return STUCK_SHORT_PNL
    if row['stuck_long']:
        return STUCK_LONG_PNL
    # Normal simulation
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

def sim_original(row):
    """Original backtest (stuck = 0% loss)."""
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

def sim_exclude(row):
    """Exclude stuck trades entirely."""
    if row['stuck']:
        return 0  # no trade
    return sim_original(row)

def sim_unlock(row):
    """Unlock strategy: for stuck, enter at limit-1tick when unlocked."""
    if row['stuck_short']:
        # Don't enter at open. Wait for unlock.
        # If day_low < 漲停: it unlocked. Enter at 漲停 - 1tick.
        zt = row['zhangting']
        tick = get_tick(zt)
        entry = zt - tick
        sl_price = zt  # re-lock = SL
        tp_price = entry * (1 - TP)
        lo = row['day_low']; cl = row['day_close']
        
        if np.isclose(cl, zt, rtol=0.001):
            # Re-locked at close: SL hit
            return (entry - sl_price) / entry - 2*COST
        elif lo <= tp_price:
            return (entry - tp_price) / entry - 2*COST
        else:
            return (entry - cl) / entry - 2*COST
    elif row['stuck_long']:
        dd = row['dieding']
        tick = get_tick(dd)
        entry = dd + tick
        sl_price = dd
        tp_price = entry * (1 + TP)
        hi = row['day_high']; cl = row['day_close']
        
        if np.isclose(cl, dd, rtol=0.001):
            return (sl_price - entry) / entry - 2*COST
        elif hi >= tp_price:
            return (tp_price - entry) / entry - 2*COST
        else:
            return (cl - entry) / entry - 2*COST
    else:
        return sim_original(row)

df['pnl_original'] = df.apply(sim_original, axis=1)
df['pnl_corrected'] = df.apply(sim_corrected, axis=1)
df['pnl_exclude'] = df.apply(sim_exclude, axis=1)
df['pnl_unlock'] = df.apply(sim_unlock, axis=1)

# Compounding
def compound(trades, pnl_col, label):
    trades = trades.copy()
    trades['ret'] = trades[pnl_col] * 0.05
    active = trades[trades['ret'] != 0].sort_values('date')
    daily = active.groupby(active['date'].dt.date)['ret'].sum().sort_index()
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
    wr = (active[pnl_col]>0).mean()*100
    print(f"\n{label}:")
    print(f"  CAGR: {cagr:.1f}% | MDD: {mdd*100:.2f}% | WR: {wr:.1f}% | Trades: {len(active)}")
    prev = 4_500_000
    for yr in sorted(yearly_cap.keys()):
        yr_ret = (yearly_cap[yr]/prev - 1)*100
        print(f"  {yr}: {yr_ret:+.1f}%")
        prev = yearly_cap[yr]
    return cagr, mdd

print("=" * 70)
print("CORRECTED BACKTEST (stuck trades = actual next-day PnL)")
print("=" * 70)

compound(df, 'pnl_original', "A) ORIGINAL backtest (stuck = 0%, OPTIMISTIC)")
compound(df, 'pnl_corrected', "B) CORRECTED (stuck = -5%, realistic)")
compound(df, 'pnl_exclude', "C) EXCLUDE stuck (skip these trades)")
compound(df, 'pnl_unlock', "D) UNLOCK strategy (enter only when unlocked)")
