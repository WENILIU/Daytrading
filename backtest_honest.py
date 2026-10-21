"""
Correct backtest: ALL trades enter at 9:00.
At 9:05 decisions use ACTUAL 9:05 prices for PnL.
- Exit if adverse >1%: PnL = actual loss at 9:05
- Add if favorable: added position uses 9:05 as entry
- Hold: normal PnL from 9:00 entry
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
has_data['entry_905'] = has_data['entry'] * (1 + has_data['price_chg_5min'])
has_data = has_data[has_data['entry_905'] > 0].copy()

COST = 0.0017; SL = 0.06; TP = 0.04

def sim_full(row):
    """
    Full simulation with 9:05 decision:
    - SHORT: if price_905 > entry*1.01 -> exit at 9:05 (small loss)
    - SHORT: if price_905 < entry*0.995 -> base PnL + added PnL (9:05 entry)
    - LONG: if price_905 < entry*0.99 -> exit at 9:05
    - LONG: if price_905 > entry*1.01 -> base PnL + added PnL
    - Otherwise: normal hold
    Returns (base_pnl, added_pnl, action)
    """
    entry = row['entry']
    entry_905 = row['entry_905']
    pc5 = row['price_chg_5min']
    d = row['direction']
    hi = row['day_high']
    lo = row['day_low']
    cl = row['day_close']
    
    # Determine action at 9:05
    if d == 'SHORT':
        if pc5 > 0.01:
            # EXIT: price went up >1%, cut loss
            exit_price = entry_905
            base_pnl = (entry - exit_price) / entry - 2*COST
            return base_pnl, 0, 'exit'
        elif pc5 < -0.005:
            # ADD: price dropped >0.5%, confirmed reversal
            # Base position: normal hold from 9:00 entry
            sl_p = entry*(1+SL); tp_p = entry*(1-TP)
            ep = sl_p if hi>=sl_p else (tp_p if lo<=tp_p else cl)
            base_pnl = (entry - ep) / entry - 2*COST
            # Added position: enter at 9:05 price
            sl_p2 = entry_905*(1+SL); tp_p2 = entry_905*(1-TP)
            ep2 = sl_p2 if hi>=sl_p2 else (tp_p2 if lo<=tp_p2 else cl)
            added_pnl = (entry_905 - ep2) / entry_905 - 2*COST
            return base_pnl, added_pnl, 'add'
        else:
            # HOLD: normal
            sl_p = entry*(1+SL); tp_p = entry*(1-TP)
            ep = sl_p if hi>=sl_p else (tp_p if lo<=tp_p else cl)
            base_pnl = (entry - ep) / entry - 2*COST
            return base_pnl, 0, 'hold'
    else:  # LONG
        if pc5 < -0.01:
            # EXIT: price dropped >1%, cut loss
            exit_price = entry_905
            base_pnl = (exit_price - entry) / entry - 2*COST
            return base_pnl, 0, 'exit'
        elif pc5 > 0.01:
            # ADD: price rose >1%, confirmed reversal
            sl_p = entry*(1-SL); tp_p = entry*(1+TP)
            ep = sl_p if lo<=sl_p else (tp_p if hi>=tp_p else cl)
            base_pnl = (ep - entry) / entry - 2*COST
            # Added position at 9:05
            sl_p2 = entry_905*(1-SL); tp_p2 = entry_905*(1+TP)
            ep2 = sl_p2 if lo<=sl_p2 else (tp_p2 if hi>=tp_p2 else cl)
            added_pnl = (ep2 - entry_905) / entry_905 - 2*COST
            return base_pnl, added_pnl, 'add'
        else:
            # HOLD
            sl_p = entry*(1-SL); tp_p = entry*(1+TP)
            ep = sl_p if lo<=sl_p else (tp_p if hi>=tp_p else cl)
            base_pnl = (ep - entry) / entry - 2*COST
            return base_pnl, 0, 'hold'

results = has_data.apply(sim_full, axis=1)
has_data['base_pnl'] = [r[0] for r in results]
has_data['added_pnl'] = [r[1] for r in results]
has_data['action'] = [r[2] for r in results]

# Position sizing: base=5%, added=2% (total 7% for confirmed)
BASE_POS = 0.05
ADD_POS = 0.02

has_data['total_ret'] = has_data['base_pnl'] * BASE_POS + has_data['added_pnl'] * ADD_POS
has_data['win'] = ((has_data['base_pnl'] * BASE_POS + has_data['added_pnl'] * ADD_POS) > 0).astype(int)
has_data['year'] = has_data['date'].dt.year

# Also compute pure baseline for comparison
def sim_baseline(row):
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

has_data['baseline_pnl'] = has_data.apply(sim_baseline, axis=1)
has_data['baseline_win'] = (has_data['baseline_pnl'] > 0).astype(int)
has_data['baseline_ret'] = has_data['baseline_pnl'] * BASE_POS

print("=" * 70)
print("HONEST COMPARISON (all PnL uses actual entry prices)")
print("=" * 70)
print()

# Action breakdown
print("=== 9:05 Action Breakdown ===")
for act in ['exit','add','hold']:
    sub = has_data[has_data['action']==act]
    if len(sub)==0: continue
    wr = sub['win'].mean()*100
    pnl = sub['total_ret'].mean()*100
    print(f"  {act.upper():5s}: {len(sub):4d} trades ({len(sub)/len(has_data)*100:.0f}%), WR={wr:.1f}%, avg ret={pnl:+.3f}%")
print()

# Overall comparison
print("=== OVERALL ===")
print(f"Baseline (no 9:05 logic): {len(has_data)} trades, WR={has_data['baseline_win'].mean()*100:.1f}%, avg PnL={has_data['baseline_pnl'].mean()*100:+.2f}%")
print(f"With 9:05 management:     {len(has_data)} trades, WR={has_data['win'].mean()*100:.1f}%, avg ret={has_data['total_ret'].mean()*100:+.3f}%")
print()

# Compounding
def compound(trades, ret_col, label):
    trades = trades.copy().sort_values('date')
    daily = trades.groupby(trades['date'].dt.date)[ret_col].sum().sort_index()
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
    prev = 4_500_000
    for yr in sorted(yearly_cap.keys()):
        yr_ret = (yearly_cap[yr]/prev - 1)*100
        n = len(trades[trades['year']==yr])
        wr = (trades[trades['year']==yr]['win']>0).mean()*100 if 'win' in trades.columns else 0
        print(f"  {yr}: {n:4d} trades, Return={yr_ret:+.1f}%")
        prev = yearly_cap[yr]
    return cagr, mdd

compound(has_data, 'baseline_ret', "A) BASELINE (enter 9:00, hold normally)")
compound(has_data, 'total_ret', "B) 9:05 DYNAMIC (exit bad, add good, hold rest)")

# Also test: just the exit filter (no adding)
has_data['exit_only_ret'] = has_data.apply(
    lambda r: r['base_pnl'] * BASE_POS if r['action'] != 'add' else r['base_pnl'] * BASE_POS, axis=1)
# Actually exit_only is same as baseline for non-exit trades, and exit trades have small loss
# The difference from baseline: exit trades lose ~1% instead of potentially -6%
has_data['exit_only_ret'] = has_data['base_pnl'] * BASE_POS  # base_pnl already accounts for exit
compound(has_data, 'exit_only_ret', "C) EXIT ONLY (cut losers at 9:05, no adding)")
