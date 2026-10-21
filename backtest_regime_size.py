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

sigs['date_dt'] = pd.to_datetime(sigs['date'])
sigs = sigs.merge(daily_mkt[['date', 'market_index', 'ma20', 'ma60', 'pct_from_high', 'market_ret']], 
                  left_on='date_dt', right_on='date', how='left', suffixes=('', '_mkt'))
sigs = sigs.dropna(subset=['ma20'])

sigs_sorted = sigs.sort_values(['date', 'abs_gap'], ascending=[True, False])
sigs_top = sigs_sorted.groupby('date').head(15).copy()

def kelly_tier(abs_gap):
    if abs_gap > 0.09: return 2.5
    if abs_gap > 0.08: return 2.0
    if abs_gap > 0.07: return 1.8
    if abs_gap > 0.065: return 1.5
    if abs_gap > 0.06: return 1.2
    return 1.0

def backtest(sigs_df, size_func, capital=4_500_000, base_pct=0.05, max_exposure=0.70, cost=0.0017):
    daily_returns = []
    for date, day in sigs_df.groupby('date'):
        day = day.copy()
        day['tier'] = day.apply(size_func, axis=1)
        day = day[day['tier'] > 0]
        if len(day) == 0:
            daily_returns.append(0)
            continue
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

# === SIZING FUNCTIONS ===

def size_kelly_only(row):
    return kelly_tier(row['abs_gap'])

def size_kelly_plus_regime(row):
    """Kelly + market regime multiplier"""
    base = kelly_tier(row['abs_gap'])
    # Favorable: market below MA20 -> boost 20%
    # Unfavorable: market above MA20 + up -> reduce 20%
    if row['direction'] == 'SHORT':
        if row['market_index'] < row['ma20']:
            return base * 1.2  # favorable for SHORT
        elif row['market_index'] > row['ma20'] and row['market_ret'] > 0.01:
            return base * 0.8  # unfavorable for SHORT
    elif row['direction'] == 'LONG':
        if row['market_index'] > row['ma20']:
            return base * 1.2  # favorable for LONG
        elif row['market_index'] < row['ma20'] and row['market_ret'] < -0.01:
            return base * 0.8  # unfavorable for LONG
    return base

def size_kelly_plus_vol(row):
    """Kelly + volatility boost (high vol = more opportunity)"""
    base = kelly_tier(row['abs_gap'])
    # High vol days have higher WR - boost slightly
    # We don't have vol_5 here, use market_ret magnitude as proxy
    if abs(row['market_ret']) > 0.015:
        return base * 1.15
    return base

def size_kelly_plus_momentum(row):
    """Kelly + gap-against-market-momentum boost"""
    base = kelly_tier(row['abs_gap'])
    # The core insight: strategy works best when gap is AGAINST market
    # SHORT (gap up) + market down = gap against market = boost
    # LONG (gap down) + market up = gap against market = boost
    if row['direction'] == 'SHORT' and row['market_ret'] < -0.005:
        return base * 1.3
    if row['direction'] == 'LONG' and row['market_ret'] > 0.005:
        return base * 1.3
    return base

def size_kelly_full_regime(row):
    """Kelly + full regime: combine MA position + direction + market gap"""
    base = kelly_tier(row['abs_gap'])
    mult = 1.0
    
    if row['direction'] == 'SHORT':
        # SHORT is best when: market weak (below MA20) + market gaps down
        if row['market_index'] < row['ma20']:
            mult *= 1.15
        if row['market_ret'] < -0.01:
            mult *= 1.2
        # SHORT is worst when: market strong + gaps up
        if row['market_index'] > row['ma20'] and row['market_ret'] > 0.01:
            mult *= 0.7
    elif row['direction'] == 'LONG':
        # LONG is best when: market strong (above MA20) + market gaps up
        if row['market_index'] > row['ma20']:
            mult *= 1.15
        if row['market_ret'] > 0.01:
            mult *= 1.2
        # LONG is worst when: market weak + gaps down
        if row['market_index'] < row['ma20'] and row['market_ret'] < -0.01:
            mult *= 0.7
    
    return base * mult

# Run all
print("=" * 80)
print("REGIME-AWARE POSITION SIZING (Kelly + market context)")
print("=" * 80)

tests = [
    ("Kelly only (baseline)", size_kelly_only),
    ("Kelly + MA20 regime", size_kelly_plus_regime),
    ("Kelly + vol boost", size_kelly_plus_vol),
    ("Kelly + momentum (gap vs mkt)", size_kelly_plus_momentum),
    ("Kelly + full regime", size_kelly_full_regime),
]

print(f"\n{'Sizing':<35} {'CAGR':>8} {'MDD':>8} {'Sharpe':>8}")
print("-" * 65)

for name, func in tests:
    cagr, mdd, sharpe, rets = backtest(sigs_top, func)
    print(f"{name:<35} {cagr*100:>7.1f}% {mdd*100:>7.1f}% {sharpe:>7.2f}")

# Best one yearly
print(f"\n{'='*80}")
print("BEST: Kelly + momentum (gap vs market direction)")
print(f"{'='*80}")
cagr, mdd, sharpe, rets = backtest(sigs_top, size_kelly_plus_momentum)
print(f"CAGR: {cagr*100:.1f}% | MDD: {mdd*100:.1f}% | Sharpe: {sharpe:.2f}")

sigs_dates = sorted(sigs_top['date'].unique())
rets_df = pd.DataFrame({'date': sigs_dates, 'ret': rets})
rets_df['date'] = pd.to_datetime(rets_df['date'])
rets_df['year'] = rets_df['date'].dt.year
yearly = rets_df.groupby('year')['ret'].apply(lambda x: (1+x).prod()-1)
print("\nYearly:")
for y, r in yearly.items():
    print(f"  {y}: {r*100:+.1f}%")
