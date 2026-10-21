import pandas as pd
import numpy as np

sigs = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")

def calc_pnl(row):
    entry = row['entry']
    direction = row['direction']
    sl_pct, tp_pct = 0.06, 0.04
    if direction == 'SHORT':
        sl_price = entry * (1 + sl_pct)
        tp_price = entry * (1 - tp_pct)
        hit_tp = row['day_low'] <= tp_price
        hit_sl = row['day_high'] >= sl_price
        if hit_tp and hit_sl:
            return tp_pct if row['day_close'] < entry else -sl_pct
        elif hit_tp: return tp_pct
        elif hit_sl: return -sl_pct
        else: return (entry - row['day_close']) / entry
    else:
        sl_price = entry * (1 - sl_pct)
        tp_price = entry * (1 + tp_pct)
        hit_tp = row['day_high'] >= tp_price
        hit_sl = row['day_low'] <= sl_price
        if hit_tp and hit_sl:
            return tp_pct if row['day_close'] > entry else -sl_pct
        elif hit_tp: return tp_pct
        elif hit_sl: return -sl_pct
        else: return (row['day_close'] - entry) / entry

sigs['pnl'] = sigs.apply(calc_pnl, axis=1)
sigs['abs_gap'] = sigs['adj_gap'].abs()

# Top 15 per day
sigs_sorted = sigs.sort_values(['date', 'abs_gap'], ascending=[True, False])
sigs_top = sigs_sorted.groupby('date').head(15).copy()

# Define position sizing schemes
def size_current(row):
    """Current Plan B: 1.0x for 5-7%, 1.5x for >7%"""
    if row['abs_gap'] > 0.07: return 1.5
    return 1.0

def size_kelly_full(row):
    """Full Kelly proportional"""
    g = row['abs_gap']
    if g > 0.09: return 2.5
    if g > 0.08: return 2.0
    if g > 0.07: return 1.8
    if g > 0.065: return 1.5
    if g > 0.06: return 1.2
    return 1.0

def size_kelly_half(row):
    """Half Kelly (conservative)"""
    g = row['abs_gap']
    if g > 0.09: return 1.8
    if g > 0.08: return 1.5
    if g > 0.07: return 1.3
    if g > 0.065: return 1.15
    if g > 0.06: return 1.05
    return 1.0

def size_wr_inverse(row):
    """Inverse win-rate: more on high WR (small gaps)"""
    g = row['abs_gap']
    if g < 0.055: return 1.5
    if g < 0.06: return 1.3
    if g < 0.07: return 1.0
    if g < 0.08: return 0.8
    return 0.6

def size_ev_optimal(row):
    """EV-weighted: proportional to expected value"""
    g = row['abs_gap']
    # EV values from analysis (normalized to 1.0 at 5-5.5%)
    if g > 0.09: return 1.87  # EV 0.0141 / 0.0075
    if g > 0.08: return 1.81  # EV 0.0137 / 0.0075
    if g > 0.07: return 1.62  # EV 0.0122 / 0.0075
    if g > 0.065: return 1.50
    if g > 0.06: return 1.33
    return 1.0

def size_ev_capped(row):
    """EV-weighted but capped at 1.5x, and exclude SHORT >15%"""
    if row['direction'] == 'SHORT' and row['abs_gap'] > 0.15:
        return 0  # exclude negative EV
    g = row['abs_gap']
    if g > 0.07: return 1.5
    if g > 0.06: return 1.2
    return 1.0

def size_directional(row):
    """Direction-aware: SHORT prefers 5-8%, LONG prefers 6-10%"""
    g = row['abs_gap']
    d = row['direction']
    if d == 'SHORT':
        if g > 0.15: return 0  # negative EV
        if g > 0.09: return 1.2  # lower WR but still positive EV
        if g > 0.07: return 1.5
        if g > 0.055: return 1.2
        return 1.0
    else:  # LONG
        if g > 0.15: return 1.5  # LONG large gaps have 61% WR!
        if g > 0.09: return 1.5
        if g > 0.07: return 1.3
        if g > 0.06: return 1.1
        return 1.0

schemes = {
    'Plan B (current)': size_current,
    'Full Kelly': size_kelly_full,
    'Half Kelly': size_kelly_half,
    'WR-inverse': size_wr_inverse,
    'EV-weighted': size_ev_optimal,
    'EV-capped': size_ev_capped,
    'Directional': size_directional,
}

# Backtest each scheme
def backtest(sigs_df, size_func, capital=4500000, base_pct=0.05, max_exposure=0.70, cost=0.0017):
    daily_returns = []
    for date, day in sigs_df.groupby('date'):
        day = day.copy()
        day['size'] = day.apply(size_func, axis=1)
        day = day[day['size'] > 0]  # remove excluded
        
        if len(day) == 0:
            daily_returns.append(0)
            continue
        
        # Sort by abs_gap descending (priority)
        day = day.sort_values('abs_gap', ascending=False)
        
        # Apply exposure cap
        total_exposure = 0
        day_pnl = 0
        for _, trade in day.iterrows():
            pos_pct = base_pct * trade['size']
            if total_exposure + pos_pct > max_exposure:
                break
            total_exposure += pos_pct
            net_pnl = trade['pnl'] - cost
            day_pnl += pos_pct * net_pnl
        
        daily_returns.append(day_pnl)
    
    returns = pd.Series(daily_returns)
    # CAGR
    years = len(returns) / 252
    total_growth = (1 + returns).prod()
    cagr = total_growth ** (1/years) - 1 if years > 0 else 0
    
    # MDD
    cum = (1 + returns).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    mdd = dd.min()
    
    # Sharpe
    sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    
    return cagr, mdd, sharpe, returns

print("=" * 80)
print("POSITION SIZING OPTIMIZATION")
print("=" * 80)
print(f"{'Scheme':<20} {'CAGR':>8} {'MDD':>8} {'Sharpe':>8} {'Avg/Day':>8}")
print("-" * 80)

results = {}
for name, func in schemes.items():
    cagr, mdd, sharpe, rets = backtest(sigs_top, func)
    results[name] = (cagr, mdd, sharpe, rets)
    print(f"{name:<20} {cagr*100:>7.1f}% {mdd*100:>7.1f}% {sharpe:>7.2f} {rets.mean()*100:>7.3f}%")

# Best scheme detailed analysis
best_name = max(results, key=lambda k: results[k][2])  # highest Sharpe
print(f"\n{'='*80}")
print(f"BEST BY SHARPE: {best_name}")
print(f"{'='*80}")

cagr, mdd, sharpe, rets = results[best_name]
print(f"CAGR: {cagr*100:.1f}% | MDD: {mdd*100:.1f}% | Sharpe: {sharpe:.2f}")

# Yearly breakdown
rets_series = rets.copy()
sigs_dates = sorted(sigs_top['date'].unique())
rets_df = pd.DataFrame({'date': sigs_dates, 'ret': rets_series})
rets_df['date'] = pd.to_datetime(rets_df['date'])
rets_df['year'] = rets_df['date'].dt.year

yearly = rets_df.groupby('year')['ret'].apply(lambda x: (1+x).prod()-1)
print("\nYearly:")
for y, r in yearly.items():
    print(f"  {y}: {r*100:+.1f}%")
