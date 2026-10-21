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

# Top 15 per day by abs_gap
sigs_sorted = sigs.sort_values(['date', 'abs_gap'], ascending=[True, False])
sigs_top = sigs_sorted.groupby('date').head(15).copy()

# Kelly 6-tier sizing
def kelly_tier(abs_gap):
    if abs_gap > 0.09: return 2.5
    if abs_gap > 0.08: return 2.0
    if abs_gap > 0.07: return 1.8
    if abs_gap > 0.065: return 1.5
    if abs_gap > 0.06: return 1.2
    return 1.0

# Plan B for comparison
def planb_tier(abs_gap):
    return 1.5 if abs_gap > 0.07 else 1.0

# === PRACTICAL BACKTEST with 整張 constraints ===
CAPITAL = 4_500_000
COST = 0.0017  # 0.17% per trade
BASE_PCT = 0.05  # 5% base position
MAX_EXPOSURE = 0.70  # 70% max exposure
MIN_LOT = 1000  # 1 lot = 1000 shares

def backtest_lot(sigs_df, tier_func, capital=CAPITAL, base_pct=BASE_PCT, 
                 max_exposure=MAX_EXPOSURE, cost=COST):
    """Backtest with whole-lot (整張) constraints."""
    daily_results = []
    
    for date, day in sigs_df.groupby('date'):
        day = day.copy()
        day['tier'] = day['abs_gap'].apply(tier_func)
        day = day.sort_values('abs_gap', ascending=False)
        
        available_capital = capital * max_exposure
        day_pnl = 0
        trades = 0
        
        for _, trade in day.iterrows():
            # Target position value
            target_value = capital * base_pct * trade['tier']
            
            # Calculate shares (整張: must be multiple of 1000)
            entry_price = trade['entry']
            if entry_price <= 0:
                continue
            
            lots = int(target_value / (entry_price * MIN_LOT))
            if lots < 1:
                continue  # Can't afford even 1 lot
            
            shares = lots * MIN_LOT
            position_value = shares * entry_price
            
            # Check exposure limit
            if position_value > available_capital:
                # Reduce lots to fit
                lots = int(available_capital / (entry_price * MIN_LOT))
                if lots < 1:
                    continue
                shares = lots * MIN_LOT
                position_value = shares * entry_price
            
            available_capital -= position_value
            
            # PnL in dollars
            pnl_pct = trade['pnl'] - cost
            pnl_dollar = position_value * pnl_pct
            day_pnl += pnl_dollar
            trades += 1
            
            if available_capital <= 0:
                break
        
        daily_return = day_pnl / capital
        daily_results.append({
            'date': date,
            'return': daily_return,
            'trades': trades,
            'pnl_dollar': day_pnl
        })
    
    df = pd.DataFrame(daily_results)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    
    # CAGR
    total_days = len(df)
    years = total_days / 252
    cum = (1 + df['return']).cumprod()
    final_value = cum.iloc[-1] if len(cum) > 0 else 1
    cagr = final_value ** (1/years) - 1 if years > 0 else 0
    
    # MDD
    peak = cum.cummax()
    dd = (cum - peak) / peak
    mdd = dd.min()
    
    # Sharpe
    sharpe = df['return'].mean() / df['return'].std() * np.sqrt(252) if df['return'].std() > 0 else 0
    
    return cagr, mdd, sharpe, df

# Run both
print("=" * 80)
print("PRACTICAL BACKTEST: 450萬 + 整張限制")
print("=" * 80)

cagr_b, mdd_b, sharpe_b, df_b = backtest_lot(sigs_top, planb_tier)
cagr_k, mdd_k, sharpe_k, df_k = backtest_lot(sigs_top, kelly_tier)

print(f"\n{'Scheme':<20} {'CAGR':>8} {'MDD':>8} {'Sharpe':>8} {'Avg Trades/Day':>14}")
print("-" * 65)
print(f"{'Plan B (1.0/1.5x)':<20} {cagr_b*100:>7.1f}% {mdd_b*100:>7.1f}% {sharpe_b:>7.2f} {df_b['trades'].mean():>14.1f}")
print(f"{'Kelly 6-tier':<20} {cagr_k*100:>7.1f}% {mdd_k*100:>7.1f}% {sharpe_k:>7.2f} {df_k['trades'].mean():>14.1f}")

# Final capital
print(f"\nFinal capital (Plan B): {CAPITAL * (1+cagr_b)**((len(df_b))/252):,.0f}")
print(f"Final capital (Kelly):  {CAPITAL * (1+cagr_k)**((len(df_k))/252):,.0f}")

# Yearly comparison
print(f"\n{'='*80}")
print("YEARLY COMPARISON (整張)")
print(f"{'='*80}")

for df, name in [(df_b, 'PlanB'), (df_k, 'Kelly')]:
    df['year'] = df['date'].dt.year

merged = df_b.groupby('date')['return'].sum().reset_index()
merged['date'] = pd.to_datetime(merged['date'])
merged['year'] = merged['date'].dt.year
yearly_b = merged.groupby('year')['return'].apply(lambda x: (1+x).prod()-1)

merged_k = df_k.groupby('date')['return'].sum().reset_index()
merged_k['date'] = pd.to_datetime(merged_k['date'])
merged_k['year'] = merged_k['date'].dt.year
yearly_k = merged_k.groupby('year')['return'].apply(lambda x: (1+x).prod()-1)

print(f"\n{'Year':<6} {'PlanB':>8} {'Kelly':>8} {'Diff':>8} {'Trades_B':>8} {'Trades_K':>8}")
print("-" * 55)

trades_b = df_b.groupby('date')['trades'].sum().reset_index()
trades_b['year'] = pd.to_datetime(trades_b['date']).dt.year
trades_k = df_k.groupby('date')['trades'].sum().reset_index()
trades_k['year'] = pd.to_datetime(trades_k['date']).dt.year

for y in sorted(yearly_b.index):
    rb = yearly_b.get(y, 0)
    rk = yearly_k.get(y, 0)
    tb = trades_b[trades_b['year']==y]['trades'].sum()
    tk = trades_k[trades_k['year']==y]['trades'].sum()
    print(f"{y:<6} {rb*100:>+7.1f}% {rk*100:>+7.1f}% {(rk-rb)*100:>+7.1f}% {tb:>8.0f} {tk:>8.0f}")

# Monthly for Kelly
print(f"\n{'='*80}")
print("KELLY MONTHLY (整張)")
print(f"{'='*80}")
df_k['year'] = df_k['date'].dt.year
df_k['month'] = df_k['date'].dt.month
monthly = df_k.groupby(['year','month'])['return'].apply(lambda x: (1+x).prod()-1).unstack(fill_value=0)

print(f"{'Year':<6}", end='')
for m in range(1,13):
    print(f"{m:>6}", end='')
print(f"{'Year':>8}")
print("-" * 90)

for y in monthly.index:
    print(f"{y:<6}", end='')
    year_total = 1
    for m in range(1,13):
        r = monthly.loc[y, m] if m in monthly.columns else 0
        year_total *= (1 + r)
        print(f"{r*100:>+6.1f}", end='')
    print(f"{(year_total-1)*100:>+8.1f}%")
