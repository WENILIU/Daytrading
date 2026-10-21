import pickle, pandas as pd, numpy as np

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'

sig = pd.read_pickle(f'{OUTPUT_DIR}/gap_fade_signals_2010.pkl')
sig['date'] = pd.to_datetime(sig['date'])

CAPITAL = 4_500_000
SL_PCT = 0.06
TP_PCT = 0.04
GAP_THRESHOLD = 0.05
MIN_PRICE = 30
MAX_PRICE = 225
MAX_POS = 10
MAX_EXP = 0.50
COST = 0.0017
BASE_POS_HIGH = 0.05
BASE_POS_LOW = 0.025

print('=' * 70)
print('GAP FADE v3 — SHORT + LONG (450萬, 整張)')
print('=' * 70)

# === SHORT ===
short = sig[sig['direction'] == 'SHORT'].copy()
short = short[short['adj_gap'] >= GAP_THRESHOLD]
short = short[(short['entry'] >= MIN_PRICE) & (short['entry'] <= MAX_PRICE)]
# SHORT: profit when price drops
sl_hit = short['day_high'] >= short['entry'] * (1 + SL_PCT)
tp_hit = short['day_low'] <= short['entry'] * (1 - TP_PCT)
short['pnl'] = np.where(tp_hit, TP_PCT, np.where(sl_hit, -SL_PCT, (short['entry'] - short['day_close']) / short['entry'])) - COST

# === LONG ===
long = sig[sig['direction'] == 'LONG'].copy()
long = long[long['adj_gap'] <= -GAP_THRESHOLD]
long = long[(long['entry'] >= MIN_PRICE) & (long['entry'] <= MAX_PRICE)]
# LONG: profit when price rises
sl_hit_l = long['day_low'] <= long['entry'] * (1 - SL_PCT)
tp_hit_l = long['day_high'] >= long['entry'] * (1 + TP_PCT)
long['pnl'] = np.where(tp_hit_l, TP_PCT, np.where(sl_hit_l, -SL_PCT, (long['day_close'] - long['entry']) / long['entry'])) - COST

print(f'SHORT signals: {len(short)}')
print(f'LONG signals: {len(long)}')

# Combine
combined = pd.concat([short, long], ignore_index=True)

# Position sizing
combined['base_pos'] = np.where(combined['adj_gap'].abs() > 0.07, BASE_POS_HIGH, BASE_POS_LOW)

# 整張
combined['shares'] = np.floor(combined['base_pos'] * CAPITAL / combined['entry'] / 1000).astype(int) * 1000
before = len(combined)
combined = combined[combined['shares'] >= 1000]
print(f'After 整張: {len(combined)} (removed {before - len(combined)})')

combined['actual_pos_pct'] = (combined['shares'] * combined['entry']) / CAPITAL

# Daily limits
combined = combined.sort_values(['date', 'adj_gap'], ascending=[True, False], key=lambda x: x.abs() if x.name == 'adj_gap' else x)
# Re-sort properly: by date, then by abs(adj_gap) descending
combined['_abs_gap'] = combined['adj_gap'].abs()
combined = combined.sort_values(['date', '_abs_gap'], ascending=[True, False])
combined['day_rank'] = combined.groupby('date').cumcount()
combined = combined[combined['day_rank'] < MAX_POS]
combined['cum_exp'] = combined.groupby('date')['actual_pos_pct'].cumsum()
combined = combined[combined['cum_exp'] <= MAX_EXP]

print(f'Final trades: {len(combined)}')
print(f'  SHORT: {(combined["direction"]=="SHORT").sum()}')
print(f'  LONG: {(combined["direction"]=="LONG").sum()}')

# === PORTFOLIO ===
combined['dollar_pnl'] = combined['pnl'] * combined['actual_pos_pct'] * CAPITAL
daily_pnl = combined.groupby('date')['dollar_pnl'].sum()
daily_ret = daily_pnl / CAPITAL

cum = (1 + daily_ret).cumprod()
years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
cagr = cum.iloc[-1] ** (1/years) - 1
mdd = ((cum - cum.cummax()) / cum.cummax()).min()
sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
calmar = cagr / abs(mdd)

print(f'\n{"=" * 70}')
print('RESULTS (SHORT + LONG)')
print(f'{"=" * 70}')
print(f'  Period: {daily_ret.index[0].date()} to {daily_ret.index[-1].date()} ({years:.1f} years)')
print(f'  Total trades: {len(combined)}')
print(f'  Trading days: {len(daily_pnl)}')
print(f'  Trades/day: {len(combined)/len(daily_pnl):.1f}')
print(f'')
print(f'  Win Rate: {(combined["pnl"]>0).mean()*100:.1f}%')
print(f'  CAGR: {cagr*100:.1f}%')
print(f'  MDD: {mdd*100:.1f}%')
print(f'  Sharpe: {sharpe:.2f}')
print(f'  Calmar: {calmar:.1f}')
print(f'  Total PnL: {daily_pnl.sum():,.0f}')
print(f'  Final capital: {CAPITAL * cum.iloc[-1]:,.0f}')

# Direction breakdown
print(f'\n{"=" * 70}')
print('DIRECTION BREAKDOWN')
print(f'{"=" * 70}')
for d in ['SHORT', 'LONG']:
    sub = combined[combined['direction'] == d]
    print(f'  {d}: {len(sub)} trades | WR={(sub["pnl"]>0).mean()*100:.1f}% | AvgPnL={sub["pnl"].mean()*100:.2f}% | Total={sub["dollar_pnl"].sum():,.0f}')

# Annual
print(f'\n{"=" * 70}')
print('ANNUAL PERFORMANCE')
print(f'{"=" * 70}')
print(f'  {"Year":<6} {"Return%":>8} {"Trades":>7} {"WR%":>6} {"AvgPnL%":>8} {"MDD%":>7}')
for yr in sorted(daily_pnl.index.year.unique()):
    yr_pnl = daily_pnl[daily_pnl.index.year == yr]
    yr_ret = yr_pnl.sum() / CAPITAL * 100
    yr_trades = len(combined[combined['date'].dt.year == yr])
    yr_wr = (combined[combined['date'].dt.year == yr]['pnl'] > 0).mean() * 100
    yr_avg = combined[combined['date'].dt.year == yr]['pnl'].mean() * 100
    yr_mdd = ((yr_pnl.cumsum() - yr_pnl.cumsum().cummax()) / CAPITAL).min() * 100
    print(f'  {yr:<6} {yr_ret:>+8.1f} {yr_trades:>7} {yr_wr:>6.1f} {yr_avg:>8.3f} {yr_mdd:>7.1f}')

# Monthly
print(f'\n{"=" * 70}')
print('MONTHLY SUMMARY')
print(f'{"=" * 70}')
monthly_ret = daily_pnl.resample('ME').sum() / CAPITAL * 100
neg_months = (monthly_ret < 0).sum()
total_months = len(monthly_ret)
print(f'  Positive: {total_months - neg_months}/{total_months} ({(total_months-neg_months)/total_months*100:.1f}%)')
if neg_months > 0:
    neg = monthly_ret[monthly_ret < 0]
    for idx, val in neg.items():
        print(f'    NEGATIVE: {idx.strftime("%Y-%m")}: {val:.2f}%')

# Rolling
print(f'\n{"=" * 70}')
print('ROLLING RETURNS')
print(f'{"=" * 70}')
for period, label in [(63, '3M'), (126, '6M'), (252, '12M')]:
    rolling = daily_ret.rolling(period).apply(lambda x: (1+x).prod() - 1).dropna()
    print(f'  Rolling {label}: min={rolling.min()*100:.1f}% | positive={((rolling>0).mean()*100):.1f}%')
