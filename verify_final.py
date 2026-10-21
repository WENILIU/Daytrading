import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

# Current config: confirm=2.5%, tier4(3x/2x/1x), bs=8%, bl=1.5%, mp=10, me=50%
capital = 4_500_000
confirm_min = 0.025
tiers = [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)]
base_short = 0.08
base_long = 0.015
max_pos = 10
max_exp = 0.50

# Filter
subset = data[data['fav_move'] >= confirm_min].copy()
print(f"After confirm filter: {len(subset)} trades")

# Assign tier multiplier
mult = np.zeros(len(subset))
for min_move, m in sorted(tiers, reverse=True):
    cond = (subset['fav_move'].values >= min_move) & (mult == 0)
    mult[cond] = m
subset['multiplier'] = mult
subset = subset[subset['multiplier'] > 0]
print(f"After tier assignment: {len(subset)} trades")

# Position sizing
subset['pos_pct'] = np.where(subset['direction']=='SHORT', base_short, base_long) * subset['multiplier']

# Daily limits
subset = subset.sort_values(['date', 'fav_move'], ascending=[True, False])
subset['day_rank'] = subset.groupby('date').cumcount()
subset = subset[subset['day_rank'] < max_pos]
subset['cum_exp'] = subset.groupby('date')['pos_pct'].cumsum()
subset = subset[subset['cum_exp'] <= max_exp]
print(f"After daily limits: {len(subset)} trades")

# PnL
subset['dollar_pnl'] = subset['pnl'] * subset['pos_pct'] * capital
daily_pnl = subset.groupby('date')['dollar_pnl'].sum()
daily_ret = daily_pnl / capital

cum = (1 + daily_ret).cumprod()
years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
cagr = cum.iloc[-1] ** (1/years) - 1
mdd = ((cum - cum.cummax()) / cum.cummax()).min()
sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)

print(f"\n{'='*50}")
print(f"FINAL VERIFIED PERFORMANCE")
print(f"{'='*50}")
print(f"Period: {daily_ret.index[0].date()} to {daily_ret.index[-1].date()} ({years:.1f} years)")
print(f"Trades: {len(subset)}")
print(f"Win Rate: {(subset['pnl']>0).mean()*100:.1f}%")
print(f"CAGR: {cagr*100:.0f}%")
print(f"MDD: {mdd*100:.1f}%")
print(f"Sharpe: {sharpe:.1f}")
print(f"Total PnL: {daily_pnl.sum():,.0f}")
print(f"Daily Avg: {daily_pnl.mean():,.0f}")
print(f"Avg trades/day: {len(subset)/len(daily_pnl):.1f}")
print(f"Max position: {subset['pos_pct'].max()*100:.1f}% = {subset['pos_pct'].max()*capital:,.0f}")

# Annual breakdown
print(f"\nAnnual:")
annual = daily_pnl.resample('YE').agg(['sum', 'count'])
for idx, row in annual.iterrows():
    yr_ret = daily_pnl[daily_pnl.index.year==idx.year].sum() / capital * 100
    print(f"  {idx.year}: {yr_ret:+.0f}% ({int(row['count'])} days)")

# Direction breakdown
print(f"\nDirection:")
for d in ['SHORT', 'LONG']:
    sub = subset[subset['direction']==d]
    if len(sub) > 0:
        print(f"  {d}: {len(sub)} trades, WR={( sub['pnl']>0).mean()*100:.1f}%, avg_pnl={sub['pnl'].mean()*100:.2f}%")

# Tier breakdown
print(f"\nTier:")
for t, label in [(3.0, 'T5(>3%)'), (2.0, 'T4(1.5-3%)'), (1.0, 'T3(0.5-1.5%)')]:
    sub = subset[subset['multiplier']==t]
    if len(sub) > 0:
        print(f"  {label}: {len(sub)} trades, WR={(sub['pnl']>0).mean()*100:.1f}%, avg_pnl={sub['pnl'].mean()*100:.2f}%")
