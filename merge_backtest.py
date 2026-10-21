import pickle, pandas as pd, numpy as np

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'

# Load existing results (2023-05 to 2026-06)
old = pd.read_pickle(f'{OUTPUT_DIR}/full_1min_results_v3.pkl')
old['date'] = pd.to_datetime(old['date'])
print(f'Existing data: {len(old)} trades, {old["date"].min().date()} to {old["date"].max().date()}')

# Load new results (2026-07 to 2026-10)
new = pd.read_pickle(f'{OUTPUT_DIR}/full_1min_results_2026H2.pkl')
new['date'] = pd.to_datetime(new['date'])
print(f'New data: {len(new)} trades, {new["date"].min().date()} to {new["date"].max().date()}')

# Merge
combined = pd.concat([old, new], ignore_index=True)
combined = combined.sort_values('date').reset_index(drop=True)
print(f'Combined: {len(combined)} trades, {combined["date"].min().date()} to {combined["date"].max().date()}')

# Save combined
pickle.dump(combined, open(f'{OUTPUT_DIR}/full_1min_results_v3_extended.pkl', 'wb'))
print('Saved full_1min_results_v3_extended.pkl')

# === FULL BACKTEST ===
CAPITAL = 4_500_000
GAP_THRESHOLD = 0.05
CONFIRM_MIN = 0.025
BASE_SHORT = 0.08
MAX_POS = 10
MAX_EXP = 0.50
MIN_PRICE = 30
MAX_PRICE = 225
SL_PCT = 0.05
TP_PCT = 0.05
TIERS = [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)]

# Add fav_move
combined['fav_move'] = np.where(combined['direction']=='SHORT', -combined['early_move_15'], combined['early_move_15'])

# Filter: SHORT only + confirmation + price
subset = combined[combined['direction'] == 'SHORT'].copy()
subset = subset[subset['fav_move'] >= CONFIRM_MIN]
subset = subset[(subset['entry'] >= MIN_PRICE) & (subset['entry'] <= MAX_PRICE)]

# Tier multipliers
mult = np.zeros(len(subset))
for min_move, m in sorted(TIERS, reverse=True):
    cond = (subset['fav_move'].values >= min_move) & (mult == 0)
    mult[cond] = m
subset['multiplier'] = mult
subset = subset[subset['multiplier'] > 0]
subset['pos_pct'] = BASE_SHORT * subset['multiplier']

# 整張
subset['shares'] = np.floor(subset['pos_pct'] * CAPITAL / subset['entry'] / 1000).astype(int) * 1000
subset = subset[subset['shares'] >= 1000]
subset['actual_pos_pct'] = (subset['shares'] * subset['entry']) / CAPITAL

# Daily limits
subset = subset.sort_values(['date', 'fav_move'], ascending=[True, False])
subset['day_rank'] = subset.groupby('date').cumcount()
subset = subset[subset['day_rank'] < MAX_POS]
subset['cum_exp'] = subset.groupby('date')['actual_pos_pct'].cumsum()
subset = subset[subset['cum_exp'] <= MAX_EXP]

print(f'\nFinal trades: {len(subset)}')

# PnL simulation
subset['dollar_pnl'] = subset['pnl'] * subset['actual_pos_pct'] * CAPITAL
daily_pnl = subset.groupby('date')['dollar_pnl'].sum()
daily_ret = daily_pnl / CAPITAL

cum = (1 + daily_ret).cumprod()
years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
cagr = cum.iloc[-1] ** (1/years) - 1
mdd = ((cum - cum.cummax()) / cum.cummax()).min()
sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
calmar = cagr / abs(mdd)

print(f'\n{"=" * 60}')
print('FULL BACKTEST RESULTS (2023-05 to 2026-10)')
print(f'{"=" * 60}')
print(f'  Period: {daily_ret.index[0].date()} to {daily_ret.index[-1].date()} ({years:.1f} years)')
print(f'  Total trades: {len(subset)}')
print(f'  Trading days: {len(daily_pnl)}')
print(f'  Trades/day: {len(subset)/len(daily_pnl):.1f}')
print(f'')
print(f'  Win Rate: {(subset["pnl"]>0).mean()*100:.1f}%')
print(f'  CAGR: {cagr*100:.0f}%')
print(f'  MDD: {mdd*100:.1f}%')
print(f'  Sharpe: {sharpe:.1f}')
print(f'  Calmar: {calmar:.1f}')
print(f'  Total PnL: {daily_pnl.sum():,.0f}')

# Annual
print(f'\n{"=" * 60}')
print('ANNUAL PERFORMANCE')
print(f'{"=" * 60}')
for yr in sorted(daily_pnl.index.year.unique()):
    yr_pnl = daily_pnl[daily_pnl.index.year == yr]
    yr_ret = yr_pnl.sum() / CAPITAL * 100
    yr_trades = len(subset[subset['date'].dt.year == yr])
    yr_wr = (subset[subset['date'].dt.year == yr]['pnl'] > 0).mean() * 100
    yr_mdd = ((yr_pnl.cumsum() - yr_pnl.cumsum().cummax()) / CAPITAL).min() * 100
    print(f'  {yr}: {yr_ret:+6.0f}% | WR={yr_wr:.0f}% | trades={yr_trades:3d} | MDD={yr_mdd:.1f}%')

# Monthly
print(f'\n{"=" * 60}')
print('MONTHLY PERFORMANCE')
print(f'{"=" * 60}')
monthly = daily_pnl.resample('ME').agg(['sum', 'count'])
monthly_ret = daily_pnl.resample('ME').sum() / CAPITAL * 100
monthly_trades = subset.groupby(subset['date'].dt.to_period('M')).size()
for idx, val in monthly_ret.items():
    period = idx.to_period('M')
    n_trades = monthly_trades.get(period, 0)
    if val != 0 or n_trades > 0:
        bar = '+' * int(max(0, min(30, val/3))) + '-' * int(max(0, min(30, -val/3)))
        print(f'  {idx.strftime("%Y-%m")}: {val:+6.1f}% ({n_trades:3d} trades) {bar}')

# Save final results
results = {
    'daily_pnl': daily_pnl,
    'daily_ret': daily_ret,
    'cum': cum,
    'trades': subset,
    'metrics': {'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe, 'calmar': calmar,
                'win_rate': (subset['pnl']>0).mean(), 'trades': len(subset)}
}
pickle.dump(results, open(f'{OUTPUT_DIR}/final_backtest_v3_extended.pkl', 'wb'))
print(f'\nSaved final_backtest_v3_extended.pkl')
