"""
Full backtest with 9:05 confirmation filter.
Entry price = actual 9:05 price (not open).
Only for 2023+ where we have 1-min data.
"""
import pandas as pd, numpy as np

# Load signals
df = pd.read_pickle('gap_fade_signals_2010.pkl')
df['date'] = pd.to_datetime(df['date'])

# Load volume features (2023+ only)
feat = pd.read_csv('volume_features.csv', parse_dates=['date'])
feat['vol5_vs_prev'] = feat['vol_first5'] / feat['vol_prev']

# Join: match on (date, stock, direction)
feat['date_str'] = feat['date'].dt.strftime('%Y-%m-%d')
df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')

merged = df.merge(
    feat[['date_str','stock','direction','price_chg_5min','vol5_vs_prev','vol_conc_5']],
    on=['date_str','stock','direction'],
    how='left'
)

# Only signals with 1-min data
has_data = merged[merged['price_chg_5min'].notna()].copy()
print(f"Signals with 1-min data: {len(has_data)}")
print(f"  SHORT: {len(has_data[has_data['direction']=='SHORT'])}")
print(f"  LONG:  {len(has_data[has_data['direction']=='LONG'])}")
print()

# Apply 9:05 filter
# SHORT: price must drop >0.5% (price_chg_5min < -0.005)
# LONG: price must rise >1% (price_chg_5min > 0.01)
# Additional: vol5/prev < 50% (reject gap-and-go)

def apply_filter(row):
    if row['direction'] == 'SHORT':
        return row['price_chg_5min'] < -0.005 and row['vol5_vs_prev'] < 0.5
    else:  # LONG
        return row['price_chg_5min'] > 0.01 and row['vol5_vs_prev'] < 0.5

has_data['pass_filter'] = has_data.apply(apply_filter, axis=1)

# Calculate 9:05 entry price
has_data['entry_905'] = has_data['entry'] * (1 + has_data['price_chg_5min'])
has_data = has_data[has_data["entry_905"] > 0].copy()

# Simulate PnL with 9:05 entry
def simulate_pnl_905(row, sl=0.06, tp=0.04, cost=0.0017):
    entry = row['entry_905']
    d = row['direction']
    hi = row['day_high']
    lo = row['day_low']
    cl = row['day_close']
    
    if d == 'SHORT':
        sl_p = entry * (1 + sl)
        tp_p = entry * (1 - tp)
        if hi >= sl_p:
            ep = sl_p
        elif lo <= tp_p:
            ep = tp_p
        else:
            ep = cl
        return (entry - ep) / entry - 2 * cost
    else:
        sl_p = entry * (1 - sl)
        tp_p = entry * (1 + tp)
        if lo <= sl_p:
            ep = sl_p
        elif hi >= tp_p:
            ep = tp_p
        else:
            ep = cl
        return (ep - entry) / entry - 2 * cost

has_data['pnl_905'] = has_data.apply(simulate_pnl_905, axis=1)
has_data['win_905'] = (has_data['pnl_905'] > 0).astype(int)

# Also simulate original (open entry) for comparison
def simulate_pnl_orig(row, sl=0.06, tp=0.04, cost=0.0017):
    entry = row['entry']
    d = row['direction']
    hi = row['day_high']
    lo = row['day_low']
    cl = row['day_close']
    if d == 'SHORT':
        sl_p = entry * (1 + sl); tp_p = entry * (1 - tp)
        ep = sl_p if hi >= sl_p else (tp_p if lo <= tp_p else cl)
        return (entry - ep) / entry - 2 * cost
    else:
        sl_p = entry * (1 - sl); tp_p = entry * (1 + tp)
        ep = sl_p if lo <= sl_p else (tp_p if hi >= tp_p else cl)
        return (ep - entry) / entry - 2 * cost

has_data['pnl_orig'] = has_data.apply(simulate_pnl_orig, axis=1)
has_data['win_orig'] = (has_data['pnl_orig'] > 0).astype(int)

# Compare
print("=" * 70)
print("COMPARISON: Original (9:00 entry) vs Filtered (9:05 entry)")
print("=" * 70)
print()

filtered = has_data[has_data['pass_filter']].copy()
unfiltered = has_data[~has_data['pass_filter']].copy()

print(f"ALL signals (with data): {len(has_data)}")
print(f"  Original WR: {has_data['win_orig'].mean()*100:.1f}%, PnL: {has_data['pnl_orig'].mean()*100:+.2f}%")
print()
print(f"FILTERED (9:05 confirm): {len(filtered)}")
print(f"  WR: {filtered['win_905'].mean()*100:.1f}%, PnL: {filtered['pnl_905'].mean()*100:+.2f}%")
print()
print(f"SKIPPED: {len(unfiltered)}")
print(f"  WR: {unfiltered['win_orig'].mean()*100:.1f}%, PnL: {unfiltered['pnl_orig'].mean()*100:+.2f}%")
print()

# Yearly performance with compounding (450M capital)
print("=" * 70)
print("YEARLY PERFORMANCE (450M capital, compounding)")
print("=" * 70)
print()

def calc_yearly(trades, pnl_col, capital=4_500_000):
    """Calculate yearly compounding returns."""
    trades = trades.copy()
    trades['year'] = trades['date'].dt.year
    results = []
    cap = capital
    for year in sorted(trades['year'].unique()):
        yr = trades[trades['year'] == year]
        # Each trade uses a fraction of capital (Kelly-style position sizing)
        # Use 5% per trade (matching the strategy's position sizing)
        yr_pnl_pct = 0
        for _, row in yr.iterrows():
            position_size = 0.05  # 5% of capital per trade
            trade_return = row[pnl_col] * position_size
            yr_pnl_pct += trade_return
        yr_return = (1 + yr_pnl_pct) - 1
        cap *= (1 + yr_return)
        wr = yr['win_905'].mean() * 100 if 'win_905' in yr.columns else yr['win_orig'].mean() * 100
        results.append({
            'year': year, 'trades': len(yr), 'wr': wr,
            'return_pct': yr_return * 100, 'capital': cap
        })
    return pd.DataFrame(results)

# Filtered strategy
print("--- FILTERED (9:05 confirmation) ---")
yr_filtered = calc_yearly(filtered, 'pnl_905')
print(f"{'Year':<6} {'Trades':>6} {'WR%':>6} {'Return%':>9} {'Capital':>14}")
print("-" * 50)
for _, r in yr_filtered.iterrows():
    print(f"{int(r['year']):<6} {int(r['trades']):>6} {r['wr']:>5.1f}% {r['return_pct']:>+8.1f}% {r['capital']:>14,.0f}")

total_ret = (yr_filtered['capital'].iloc[-1] / 4_500_000 - 1) * 100
years = len(yr_filtered)
cagr = ((yr_filtered['capital'].iloc[-1] / 4_500_000) ** (1/years) - 1) * 100
print(f"\nTotal return: {total_ret:.1f}% | CAGR: {cagr:.1f}%")

# MDD
caps = [4_500_000] + list(yr_filtered['capital'])
peak = caps[0]
mdd = 0
for c in caps:
    if c > peak: peak = c
    dd = (c - peak) / peak
    if dd < mdd: mdd = dd
print(f"MDD (yearly): {mdd*100:.1f}%")
print()

# Original for comparison
print("--- ORIGINAL (9:00 entry, no filter) ---")
yr_orig = calc_yearly(has_data, 'pnl_orig')
print(f"{'Year':<6} {'Trades':>6} {'WR%':>6} {'Return%':>9} {'Capital':>14}")
print("-" * 50)
for _, r in yr_orig.iterrows():
    print(f"{int(r['year']):<6} {int(r['trades']):>6} {r['wr']:>5.1f}% {r['return_pct']:>+8.1f}% {r['capital']:>14,.0f}")

total_ret_o = (yr_orig['capital'].iloc[-1] / 4_500_000 - 1) * 100
cagr_o = ((yr_orig['capital'].iloc[-1] / 4_500_000) ** (1/years) - 1) * 100
print(f"\nTotal return: {total_ret_o:.1f}% | CAGR: {cagr_o:.1f}%")

caps_o = [4_500_000] + list(yr_orig['capital'])
peak_o = caps_o[0]
mdd_o = 0
for c in caps_o:
    if c > peak_o: peak_o = c
    dd = (c - peak_o) / peak_o
    if dd < mdd_o: mdd_o = dd
print(f"MDD (yearly): {mdd_o*100:.1f}%")
print()

# Daily MDD for filtered
print("--- DAILY MDD (filtered) ---")
filtered['year_month_day'] = filtered['date'].dt.date
daily = filtered.groupby('year_month_day').agg(
    day_pnl=('pnl_905', lambda x: sum(xi * 0.05 for xi in x)),
    trades=('pnl_905', 'count')
).sort_index()

cap = 4_500_000
peak = cap
mdd_daily = 0
for _, row in daily.iterrows():
    cap *= (1 + row['day_pnl'])
    if cap > peak: peak = cap
    dd = (cap - peak) / peak
    if dd < mdd_daily: mdd_daily = dd

print(f"Daily MDD: {mdd_daily*100:.2f}%")
print(f"Final capital: {cap:,.0f}")
final_cagr = ((cap / 4_500_000) ** (1/3.5) - 1) * 100  # ~3.5 years
print(f"CAGR (3.5yr): {final_cagr:.1f}%")
