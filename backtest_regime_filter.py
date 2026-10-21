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

# Build market state
daily_mkt = sigs.groupby('date').agg(market_ret=('market_ret', 'first')).reset_index()
daily_mkt['date'] = pd.to_datetime(daily_mkt['date'])
daily_mkt = daily_mkt.sort_values('date').reset_index(drop=True)
daily_mkt['market_index'] = (1 + daily_mkt['market_ret']).cumprod()
daily_mkt['ma20'] = daily_mkt['market_index'].rolling(20).mean()
daily_mkt['ma60'] = daily_mkt['market_index'].rolling(60).mean()
daily_mkt['high_20'] = daily_mkt['market_index'].rolling(20).max()
daily_mkt['pct_from_high'] = (daily_mkt['market_index'] - daily_mkt['high_20']) / daily_mkt['high_20']
daily_mkt['vol_5'] = daily_mkt['market_ret'].rolling(5).std()

# Merge market state into signals
sigs['date_dt'] = pd.to_datetime(sigs['date'])
sigs = sigs.merge(daily_mkt[['date', 'market_index', 'ma20', 'ma60', 'pct_from_high', 'vol_5', 'market_ret']], 
                  left_on='date_dt', right_on='date', how='left', suffixes=('', '_mkt'))
sigs = sigs.dropna(subset=['ma20'])

# Kelly tier
def kelly_tier(abs_gap):
    if abs_gap > 0.09: return 2.5
    if abs_gap > 0.08: return 2.0
    if abs_gap > 0.07: return 1.8
    if abs_gap > 0.065: return 1.5
    if abs_gap > 0.06: return 1.2
    return 1.0

# Backtest with lot constraints
def backtest(sigs_df, filter_func=None, size_func=kelly_tier, 
             capital=4_500_000, base_pct=0.05, max_exposure=0.70, cost=0.0017):
    daily_returns = []
    for date, day in sigs_df.groupby('date'):
        day = day.copy()
        
        # Apply regime filter
        if filter_func:
            day = day[day.apply(filter_func, axis=1)]
        
        if len(day) == 0:
            daily_returns.append(0)
            continue
        
        day['tier'] = day['abs_gap'].apply(size_func)
        day = day[day['tier'] > 0]
        day = day.sort_values('abs_gap', ascending=False)
        
        available = capital * max_exposure
        day_pnl = 0
        for _, trade in day.iterrows():
            target_val = capital * base_pct * trade['tier']
            entry_price = trade['entry']
            if entry_price <= 0: continue
            lots = int(target_val / (entry_price * 1000))
            if lots < 1: continue
            shares = lots * 1000
            pos_val = shares * entry_price
            if pos_val > available:
                lots = int(available / (entry_price * 1000))
                if lots < 1: continue
                shares = lots * 1000
                pos_val = shares * entry_price
            available -= pos_val
            day_pnl += pos_val * (trade['pnl'] - cost)
            if available <= 0: break
        
        daily_returns.append(day_pnl / capital)
    
    returns = pd.Series(daily_returns)
    years = len(returns) / 252
    cum = (1 + returns).cumprod()
    cagr = cum.iloc[-1] ** (1/years) - 1 if years > 0 else 0
    peak = cum.cummax()
    mdd = ((cum - peak) / peak).min()
    sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    return cagr, mdd, sharpe, returns

# Top 15 per day
sigs_sorted = sigs.sort_values(['date', 'abs_gap'], ascending=[True, False])
sigs_top = sigs_sorted.groupby('date').head(15).copy()

# Define filters
def no_filter(row):
    return True

def filter_short_when_market_strong(row):
    """Skip SHORT when market is above MA20 AND up >1%"""
    if row['direction'] == 'SHORT':
        if row['market_index'] > row['ma20'] and row['market_ret'] > 0.01:
            return False
    return True

def filter_long_when_market_weak(row):
    """Skip LONG when market is below MA20 AND down >1%"""
    if row['direction'] == 'LONG':
        if row['market_index'] < row['ma20'] and row['market_ret'] < -0.01:
            return False
    return True

def filter_both_directions(row):
    """Combined: skip SHORT in strong market, skip LONG in weak market"""
    if row['direction'] == 'SHORT':
        if row['market_index'] > row['ma20'] and row['market_ret'] > 0.01:
            return False
    if row['direction'] == 'LONG':
        if row['market_index'] < row['ma20'] and row['market_ret'] < -0.01:
            return False
    return True

def filter_near_high_only(row):
    """Only trade when market is NOT at 20-day high (within 1%)"""
    if row['pct_from_high'] > -0.01:
        return False
    return True

def filter_aggressive(row):
    """Skip SHORT when above MA20, skip LONG when below MA20"""
    if row['direction'] == 'SHORT' and row['market_index'] > row['ma20']:
        return False
    if row['direction'] == 'LONG' and row['market_index'] < row['ma20']:
        return False
    return True

def filter_conservative(row):
    """Only skip extreme cases: SHORT when market up>2%, LONG when market down>2%"""
    if row['direction'] == 'SHORT' and row['market_ret'] > 0.02:
        return False
    if row['direction'] == 'LONG' and row['market_ret'] < -0.02:
        return False
    return True

# Run all
print("=" * 80)
print("MARKET REGIME FILTER BACKTEST (Kelly 6-tier + 整張)")
print("=" * 80)

tests = [
    ("No filter (baseline)", no_filter),
    ("Skip SHORT: mkt>MA20 & up>1%", filter_short_when_market_strong),
    ("Skip LONG: mkt<MA20 & down>1%", filter_long_when_market_weak),
    ("Both directions", filter_both_directions),
    ("Not at 20d high", filter_near_high_only),
    ("Aggressive: SHORT only<MA20", filter_aggressive),
    ("Conservative: only extreme", filter_conservative),
]

print(f"\n{'Filter':<35} {'CAGR':>8} {'MDD':>8} {'Sharpe':>8} {'Trades':>8}")
print("-" * 75)

for name, func in tests:
    cagr, mdd, sharpe, rets = backtest(sigs_top, filter_func=func)
    total_trades = (rets != 0).sum()
    print(f"{name:<35} {cagr*100:>7.1f}% {mdd*100:>7.1f}% {sharpe:>7.2f} {total_trades:>8}")

# Best filter detailed
print(f"\n{'='*80}")
print("BEST FILTER: Both directions (skip SHORT in strong, LONG in weak)")
print(f"{'='*80}")

cagr, mdd, sharpe, rets = backtest(sigs_top, filter_func=filter_both_directions)
print(f"CAGR: {cagr*100:.1f}% | MDD: {mdd*100:.1f}% | Sharpe: {sharpe:.2f}")

# Yearly
sigs_dates = sorted(sigs_top['date'].unique())
rets_df = pd.DataFrame({'date': sigs_dates, 'ret': rets})
rets_df['date'] = pd.to_datetime(rets_df['date'])
rets_df['year'] = rets_df['date'].dt.year
yearly = rets_df.groupby('year')['ret'].apply(lambda x: (1+x).prod()-1)
print("\nYearly:")
for y, r in yearly.items():
    print(f"  {y}: {r*100:+.1f}%")
