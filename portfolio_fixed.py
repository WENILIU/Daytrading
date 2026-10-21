import pickle, pandas as pd, numpy as np

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'

# Load fixed results
df = pd.read_pickle(f'{OUTPUT_DIR}/full_1min_results_v3_fixed.pkl')
df['date'] = pd.to_datetime(df['date'])
df['fav_move'] = -df['early_move_15']

print('=' * 60)
print('PORTFOLIO BACKTEST (CORRECTED: 9:15 entry)')
print('=' * 60)

CAPITAL = 4_500_000
CONFIRM_MIN = 0.025
BASE_SHORT = 0.08
MAX_POS = 10
MAX_EXP = 0.50
MIN_PRICE = 30
MAX_PRICE = 225
TIERS = [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)]

# Filters
subset = df[df['fav_move'] >= CONFIRM_MIN].copy()
subset = subset[(subset['entry'] >= MIN_PRICE) & (subset['entry'] <= MAX_PRICE)]

# Tiers
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
print(f'Date range: {subset["date"].min().date()} to {subset["date"].max().date()}')

# PnL
subset['dollar_pnl'] = subset['pnl'] * subset['actual_pos_pct'] * CAPITAL
daily_pnl = subset.groupby('date')['dollar_pnl'].sum()
daily_ret = daily_pnl / CAPITAL

cum = (1 + daily_ret).cumprod()
years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
cagr = cum.iloc[-1] ** (1/years) - 1
mdd = ((cum - cum.cummax()) / cum.cummax()).min()
sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0
calmar = cagr / abs(mdd) if mdd != 0 else 0

print(f'\n{"=" * 60}')
print('RESULTS')
print(f'{"=" * 60}')
print(f'  Period: {daily_ret.index[0].date()} to {daily_ret.index[-1].date()} ({years:.1f} years)')
print(f'  Total trades: {len(subset)}')
print(f'  Trading days: {len(daily_pnl)}')
print(f'  Trades/day: {len(subset)/len(daily_pnl):.1f}')
print(f'')
print(f'  Win Rate: {(subset["pnl"]>0).mean()*100:.1f}%')
print(f'  CAGR: {cagr*100:.1f}%')
print(f'  MDD: {mdd*100:.1f}%')
print(f'  Sharpe: {sharpe:.1f}')
print(f'  Calmar: {calmar:.1f}')
print(f'  Total PnL: {daily_pnl.sum():,.0f}')
print(f'  Avg PnL/trade: {subset["pnl"].mean()*100:.3f}%')

# Exit reason breakdown
print(f'\n{"=" * 60}')
print('EXIT REASON BREAKDOWN')
print(f'{"=" * 60}')
for reason in ['TP', 'SL', 'FORCE']:
    sub = subset[subset['exit_reason'] == reason]
    if len(sub) > 0:
        print(f'  {reason}: {len(sub):4d} trades ({len(sub)/len(subset)*100:.0f}%) | avg PnL={sub["pnl"].mean()*100:.2f}%')

# Annual
print(f'\n{"=" * 60}')
print('ANNUAL PERFORMANCE')
print(f'{"=" * 60}')
for yr in sorted(daily_pnl.index.year.unique()):
    yr_pnl = daily_pnl[daily_pnl.index.year == yr]
    yr_ret = yr_pnl.sum() / CAPITAL * 100
    yr_trades = len(subset[subset['date'].dt.year == yr])
    yr_wr = (subset[subset['date'].dt.year == yr]['pnl'] > 0).mean() * 100
    print(f'  {yr}: {yr_ret:+6.1f}% | WR={yr_wr:.0f}% | trades={yr_trades:3d}')

# Monthly (last 6 months)
print(f'\n{"=" * 60}')
print('MONTHLY (last 6 months)')
print(f'{"=" * 60}')
monthly_ret = daily_pnl.resample('ME').sum() / CAPITAL * 100
for idx, val in monthly_ret.tail(6).items():
    print(f'  {idx.strftime("%Y-%m")}: {val:+6.1f}%')

# October 2026 detail
print(f'\n{"=" * 60}')
print('OCTOBER 2026 TRADES')
print(f'{"=" * 60}')
oct_trades = subset[(subset['date'] >= '2026-10-01')]
for _, row in oct_trades.iterrows():
    d = row['date'].strftime('%m/%d')
    result = 'W' if row['pnl'] > 0 else 'L'
    print(f'  {d} | {row["stock"]} | entry={row["entry"]:.1f} | PnL={row["pnl"]*100:+.2f}% | {row["exit_reason"]} | {result}')
