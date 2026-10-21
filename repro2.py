import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

capital = 5_000_000

def sim(trade_data, confirm_min, tiers, base_short, base_long, max_pos, max_exp, capital):
    subset = trade_data[trade_data['fav_move'] >= confirm_min].copy()
    if len(subset) == 0: return None
    mult = np.zeros(len(subset))
    for min_move, m in sorted(tiers, reverse=True):
        cond = (subset['fav_move'].values >= min_move) & (mult == 0)
        mult[cond] = m
    subset['multiplier'] = mult
    subset = subset[subset['multiplier'] > 0]
    if len(subset) == 0: return None
    subset['pos_pct'] = np.where(subset['direction']=='SHORT', base_short, base_long) * subset['multiplier']
    subset = subset.sort_values(['date', 'fav_move'], ascending=[True, False])
    subset['day_rank'] = subset.groupby('date').cumcount()
    subset = subset[subset['day_rank'] < max_pos]
    subset['cum_exp'] = subset.groupby('date')['pos_pct'].cumsum()
    subset = subset[subset['cum_exp'] <= max_exp]
    if len(subset) == 0: return None
    subset['dollar_pnl'] = subset['pnl'] * subset['pos_pct'] * capital
    daily_pnl = subset.groupby('date')['dollar_pnl'].sum()
    daily_ret = daily_pnl / capital
    cum = (1 + daily_ret).cumprod()
    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
    if years < 0.3 or cum.iloc[-1] <= 0: return None
    cagr = cum.iloc[-1] ** (1/years) - 1
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0
    return {'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe, 'trades': len(subset),
            'win_rate': (subset['pnl'] > 0).mean(), 'daily_avg': daily_pnl.mean(),
            'total_pnl': daily_pnl.sum(), 'days': len(daily_pnl)}

# The target has 7 trades/day and WR 84.8%
# With confirm=0, we get 3794 trades / 635 days = 6 trades/day, WR 53.7%
# WR 84.8% requires confirm >= 2.5%... but that gives only 2 trades/day
# 
# UNLESS: the previous simulation used a DIFFERENT pnl calculation
# Maybe it used day_close (force close) instead of actual SL/TP hits
# Let me check: what if pnl is calculated as (entry - day_close)/entry for SHORT?
# That would give different results than the 1-min simulation

# Actually, let me check if the previous result came from the gap_fade_v3_trades.pkl
# which uses daily OHLC (not 1-min). That file has 28,138 trades.
trades_v3 = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_v3_trades.pkl', 'rb'))
trades_v3['date'] = pd.to_datetime(trades_v3['date'])

# Filter to 2023-2026 only (same period as 1-min data)
recent = trades_v3[trades_v3['date'] >= '2023-01-01'].copy()
print(f"v3 trades 2023+: {len(recent)}")
print(f"WR: {(recent['pnl']>0).mean()*100:.1f}%")
print(f"Avg PnL: {recent['pnl'].mean()*100:.3f}%")

# This uses pos_pct=5.0 (5%) for all trades
# Let me simulate with 500万, 5% position, all trades
daily_pnl = recent.groupby('date').apply(lambda g: (g['pnl'] * 0.05 * capital).sum())
daily_ret = daily_pnl / capital
cum = (1 + daily_ret).cumprod()
years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
cagr = cum.iloc[-1] ** (1/years) - 1
mdd = ((cum - cum.cummax()) / cum.cummax()).min()
sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)

print(f"\n=== v3 daily signals, 5% pos, 500万 ===")
print(f"Trades: {len(recent)}, Days: {len(daily_pnl)}")
print(f"WR: {(recent['pnl']>0).mean()*100:.1f}%")
print(f"CAGR: {cagr*100:.0f}%, MDD: {mdd*100:.1f}%, Sharpe: {sharpe:.1f}")
print(f"Daily avg: {daily_pnl.mean():,.0f}, Total: {daily_pnl.sum():,.0f}")
print(f"Trades/day: {len(recent)/len(daily_pnl):.1f}")

# Now try with direction-weighted (3% short, 1.5% long) as in original config
recent2 = recent.copy()
recent2['pos'] = np.where(recent2['direction']=='SHORT', 0.03, 0.015)
daily_pnl2 = recent2.groupby('date').apply(lambda g: (g['pnl'] * g['pos'] * capital).sum())
daily_ret2 = daily_pnl2 / capital
cum2 = (1 + daily_ret2).cumprod()
cagr2 = cum2.iloc[-1] ** (1/years) - 1
mdd2 = ((cum2 - cum2.cummax()) / cum2.cummax()).min()
sharpe2 = daily_ret2.mean() / daily_ret2.std() * np.sqrt(252)

print(f"\n=== v3 daily, 3%/1.5% weighted, 500万 ===")
print(f"CAGR: {cagr2*100:.0f}%, MDD: {mdd2*100:.1f}%, Sharpe: {sharpe2:.1f}")
print(f"Daily avg: {daily_pnl2.mean():,.0f}, Total: {daily_pnl2.sum():,.0f}")

# Try with 2x short weight (as in v3 module: short=3%, long=1.5%)
# and higher: short=6%, long=3%
for sp, lp in [(0.03, 0.015), (0.05, 0.025), (0.06, 0.03), (0.08, 0.04), (0.10, 0.05)]:
    recent3 = recent.copy()
    recent3['pos'] = np.where(recent3['direction']=='SHORT', sp, lp)
    dp = recent3.groupby('date').apply(lambda g: (g['pnl'] * g['pos'] * capital).sum())
    dr = dp / capital
    c = (1 + dr).cumprod()
    cg = c.iloc[-1] ** (1/years) - 1
    md = ((c - c.cummax()) / c.cummax()).min()
    sh = dr.mean() / dr.std() * np.sqrt(252)
    print(f"\n  SHORT={sp*100:.0f}% LONG={lp*100:.1f}%: CAGR={cg*100:.0f}% MDD={md*100:.1f}% Sharpe={sh:.1f} daily={dp.mean():,.0f}")
