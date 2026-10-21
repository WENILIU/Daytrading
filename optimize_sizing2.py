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

sigs_sorted = sigs.sort_values(['date', 'abs_gap'], ascending=[True, False])
sigs_top = sigs_sorted.groupby('date').head(15).copy()

# === TEST 1: Full Kelly with practical constraints ===
def size_kelly_practical(row):
    """Full Kelly but practical: cap at 2.5x, exclude SHORT >15% (negative EV)"""
    if row['direction'] == 'SHORT' and row['abs_gap'] > 0.15:
        return 0
    g = row['abs_gap']
    if g > 0.09: return 2.5
    if g > 0.08: return 2.0
    if g > 0.07: return 1.8
    if g > 0.065: return 1.5
    if g > 0.06: return 1.2
    return 1.0

# === TEST 2: Kelly + Scaling in (if trade goes +2%, add 50% more) ===
# Simulate: if day_low < entry*0.98 for SHORT (or day_high > entry*1.02 for LONG)
# then add 50% more position at that level
def calc_pnl_with_add(row):
    """PnL with scaling in at +2% favorable move"""
    entry = row['entry']
    direction = row['direction']
    sl_pct, tp_pct = 0.06, 0.04
    add_threshold = 0.02  # add at +2%
    add_ratio = 0.5  # add 50% more
    
    if direction == 'SHORT':
        sl_price = entry * (1 + sl_pct)
        tp_price = entry * (1 - tp_pct)
        add_price = entry * (1 - add_threshold)
        
        hit_tp = row['day_low'] <= tp_price
        hit_sl = row['day_high'] >= sl_price
        hit_add = row['day_low'] <= add_price
        
        # Base position PnL
        if hit_tp and hit_sl:
            base_pnl = tp_pct if row['day_close'] < entry else -sl_pct
        elif hit_tp: base_pnl = tp_pct
        elif hit_sl: base_pnl = -sl_pct
        else: base_pnl = (entry - row['day_close']) / entry
        
        # Add position PnL (entered at add_price)
        if hit_add and not hit_sl:
            # Add was profitable
            if hit_tp:
                add_pnl = (add_price - tp_price) / add_price
            else:
                add_pnl = (add_price - row['day_close']) / add_price
        elif hit_add and hit_sl:
            # Add got stopped
            add_pnl = (add_price - sl_price) / add_price
        else:
            add_pnl = 0
        
        # Combined: base 1.0 + add 0.5
        combined = (base_pnl * 1.0 + add_pnl * add_ratio) / (1.0 + add_ratio) if hit_add else base_pnl
        return combined
    else:  # LONG
        sl_price = entry * (1 - sl_pct)
        tp_price = entry * (1 + tp_pct)
        add_price = entry * (1 + add_threshold)
        
        hit_tp = row['day_high'] >= tp_price
        hit_sl = row['day_low'] <= sl_price
        hit_add = row['day_high'] >= add_price
        
        if hit_tp and hit_sl:
            base_pnl = tp_pct if row['day_close'] > entry else -sl_pct
        elif hit_tp: base_pnl = tp_pct
        elif hit_sl: base_pnl = -sl_pct
        else: base_pnl = (row['day_close'] - entry) / entry
        
        if hit_add and not hit_sl:
            if hit_tp:
                add_pnl = (tp_price - add_price) / add_price
            else:
                add_pnl = (row['day_close'] - add_price) / add_price
        elif hit_add and hit_sl:
            add_pnl = (sl_price - add_price) / add_price
        else:
            add_pnl = 0
        
        combined = (base_pnl * 1.0 + add_pnl * add_ratio) / (1.0 + add_ratio) if hit_add else base_pnl
        return combined

sigs_top['pnl_add'] = sigs_top.apply(calc_pnl_with_add, axis=1)

# Backtest function
def backtest(sigs_df, size_func, pnl_col='pnl', capital=4500000, base_pct=0.05, max_exposure=0.70, cost=0.0017):
    daily_returns = []
    for date, day in sigs_df.groupby('date'):
        day = day.copy()
        day['size'] = day.apply(size_func, axis=1)
        day = day[day['size'] > 0]
        if len(day) == 0:
            daily_returns.append(0)
            continue
        day = day.sort_values('abs_gap', ascending=False)
        total_exposure = 0
        day_pnl = 0
        for _, trade in day.iterrows():
            pos_pct = base_pct * trade['size']
            if total_exposure + pos_pct > max_exposure:
                break
            total_exposure += pos_pct
            net_pnl = trade[pnl_col] - cost
            day_pnl += pos_pct * net_pnl
        daily_returns.append(day_pnl)
    
    returns = pd.Series(daily_returns)
    years = len(returns) / 252
    total_growth = (1 + returns).prod()
    cagr = total_growth ** (1/years) - 1 if years > 0 else 0
    cum = (1 + returns).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    mdd = dd.min()
    sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    return cagr, mdd, sharpe, returns

# Run all tests
print("=" * 80)
print("PRACTICAL OPTIMIZATION: Kelly + Scaling In")
print("=" * 80)

tests = [
    ("Plan B (1.0/1.5x)", size_current := lambda r: 1.5 if r['abs_gap'] > 0.07 else 1.0, 'pnl'),
    ("Kelly 6-tier", size_kelly_practical, 'pnl'),
    ("Kelly + Add 50%@+2%", size_kelly_practical, 'pnl_add'),
    ("Kelly + base 7%", lambda r: size_kelly_practical(r), 'pnl'),  # same but test with higher base
]

print(f"\n{'Scheme':<25} {'CAGR':>8} {'MDD':>8} {'Sharpe':>8}")
print("-" * 60)

for name, func, pnl_col in tests:
    base = 0.07 if "base 7" in name else 0.05
    cagr, mdd, sharpe, rets = backtest(sigs_top, func, pnl_col=pnl_col, base_pct=base)
    print(f"{name:<25} {cagr*100:>7.1f}% {mdd*100:>7.1f}% {sharpe:>7.2f}")

# === TEST 3: Optimal base_pct for Kelly ===
print(f"\n{'='*80}")
print("OPTIMAL BASE POSITION SIZE (Kelly 6-tier)")
print(f"{'='*80}")
print(f"{'Base%':>8} {'CAGR':>8} {'MDD':>8} {'Sharpe':>8} {'MaxExp':>8}")
print("-" * 50)

for base in [0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10]:
    for max_exp in [0.70, 0.80, 0.90]:
        cagr, mdd, sharpe, _ = backtest(sigs_top, size_kelly_practical, base_pct=base, max_exposure=max_exp)
        if mdd > -0.05:  # only show if MDD < 5%
            print(f"{base*100:>7.1f}% {cagr*100:>7.1f}% {mdd*100:>7.1f}% {sharpe:>7.2f} {max_exp*100:>7.0f}%")

# === TEST 4: Yearly comparison Plan B vs Kelly ===
print(f"\n{'='*80}")
print("YEARLY COMPARISON: Plan B vs Kelly 6-tier")
print(f"{'='*80}")

_, _, _, rets_planb = backtest(sigs_top, lambda r: 1.5 if r['abs_gap'] > 0.07 else 1.0)
_, _, _, rets_kelly = backtest(sigs_top, size_kelly_practical)

sigs_dates = sorted(sigs_top['date'].unique())
df_cmp = pd.DataFrame({'date': sigs_dates, 'planb': rets_planb, 'kelly': rets_kelly})
df_cmp['date'] = pd.to_datetime(df_cmp['date'])
df_cmp['year'] = df_cmp['date'].dt.year

yearly = df_cmp.groupby('year')[['planb', 'kelly']].apply(lambda x: pd.Series({
    'planb': (1+x['planb']).prod()-1,
    'kelly': (1+x['kelly']).prod()-1
}))

print(f"{'Year':<6} {'PlanB':>8} {'Kelly':>8} {'Diff':>8}")
print("-" * 35)
for y, row in yearly.iterrows():
    diff = row['kelly'] - row['planb']
    print(f"{y:<6} {row['planb']*100:>+7.1f}% {row['kelly']*100:>+7.1f}% {diff*100:>+7.1f}%")
