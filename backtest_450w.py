import pickle, pandas as pd, numpy as np

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'

print('=' * 70)
print('GAP FADE v3 — 450萬 實測回測 (SL6%/TP4%, 5%/2.5% 倉位)')
print('=' * 70)

# Load all daily gap signals (2010-2026)
sig = pd.read_pickle(f'{OUTPUT_DIR}/gap_fade_signals_2010.pkl')
sig['date'] = pd.to_datetime(sig['date'])
print(f'Total signals: {len(sig)}')
print(f'Date range: {sig["date"].min().date()} to {sig["date"].max().date()}')

# === STRATEGY PARAMETERS ===
CAPITAL = 4_500_000
SL_PCT = 0.06
TP_PCT = 0.04
GAP_THRESHOLD = 0.05
MIN_PRICE = 30
MAX_PRICE = 225
MAX_POS = 10
MAX_EXP = 0.50
COST = 0.0017

# Position sizing: 5% base, 2.5% for lower confidence
BASE_POS_HIGH = 0.05  # adj_gap > 7%
BASE_POS_LOW = 0.025  # adj_gap 5-7%

# === FILTER ===
# SHORT only
subset = sig[sig['direction'] == 'SHORT'].copy()
print(f'SHORT signals: {len(subset)}')

# Gap threshold
subset = subset[subset['adj_gap'] >= GAP_THRESHOLD]
print(f'After gap >= 5%: {len(subset)}')

# Price filter
subset = subset[(subset['entry'] >= MIN_PRICE) & (subset['entry'] <= MAX_PRICE)]
print(f'After price 30-225: {len(subset)}')

# === PnL CALCULATION (daily OHLC) ===
# Entry = open price
# SL: day_high >= entry * (1 + SL_PCT) -> loss
# TP: day_low <= entry * (1 - TP_PCT) -> profit
# Both hit: assume TP first (optimistic) — this is the known limitation
# Neither: force close at day_close

sl_price = subset['entry'] * (1 + SL_PCT)
tp_price = subset['entry'] * (1 - TP_PCT)

# Determine outcome
hit_sl = subset['day_high'] >= sl_price
hit_tp = subset['day_low'] <= tp_price

# PnL logic:
# If TP hit (regardless of SL): +TP_PCT (optimistic assumption)
# If only SL hit: -SL_PCT
# If neither: (entry - day_close) / entry
pnl = np.where(hit_tp, TP_PCT, 
     np.where(hit_sl, -SL_PCT, 
     (subset['entry'] - subset['day_close']) / subset['entry']))

subset['pnl'] = pnl - COST

# === POSITION SIZING ===
# Tier: adj_gap > 7% -> 5%, adj_gap 5-7% -> 2.5%
subset['base_pos'] = np.where(subset['adj_gap'] > 0.07, BASE_POS_HIGH, BASE_POS_LOW)

# 整張
subset['shares'] = np.floor(subset['base_pos'] * CAPITAL / subset['entry'] / 1000).astype(int) * 1000
before = len(subset)
subset = subset[subset['shares'] >= 1000]
print(f'After 整張 filter: {len(subset)} (removed {before - len(subset)})')

subset['actual_pos_pct'] = (subset['shares'] * subset['entry']) / CAPITAL

# === DAILY LIMITS ===
subset = subset.sort_values(['date', 'adj_gap'], ascending=[True, False])
subset['day_rank'] = subset.groupby('date').cumcount()
subset = subset[subset['day_rank'] < MAX_POS]
subset['cum_exp'] = subset.groupby('date')['actual_pos_pct'].cumsum()
subset = subset[subset['cum_exp'] <= MAX_EXP]

print(f'Final trades: {len(subset)}')
print(f'Trading days: {subset["date"].nunique()}')

# === PORTFOLIO SIMULATION ===
subset['dollar_pnl'] = subset['pnl'] * subset['actual_pos_pct'] * CAPITAL
daily_pnl = subset.groupby('date')['dollar_pnl'].sum()
daily_ret = daily_pnl / CAPITAL

cum = (1 + daily_ret).cumprod()
years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
cagr = cum.iloc[-1] ** (1/years) - 1
mdd = ((cum - cum.cummax()) / cum.cummax()).min()
sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
calmar = cagr / abs(mdd)

print(f'\n{"=" * 70}')
print('RESULTS')
print(f'{"=" * 70}')
print(f'  Period: {daily_ret.index[0].date()} to {daily_ret.index[-1].date()} ({years:.1f} years)')
print(f'  Total trades: {len(subset)}')
print(f'  Trading days: {len(daily_pnl)}')
print(f'  Trades/day: {len(subset)/len(daily_pnl):.1f}')
print(f'')
print(f'  Win Rate: {(subset["pnl"]>0).mean()*100:.1f}%')
print(f'  CAGR: {cagr*100:.1f}%')
print(f'  MDD: {mdd*100:.1f}%')
print(f'  Sharpe: {sharpe:.2f}')
print(f'  Calmar: {calmar:.1f}')
print(f'  Total PnL: {daily_pnl.sum():,.0f}')
print(f'  Final capital: {CAPITAL * cum.iloc[-1]:,.0f}')

# Annual
print(f'\n{"=" * 70}')
print('ANNUAL PERFORMANCE')
print(f'{"=" * 70}')
print(f'  {"Year":<6} {"Return%":>8} {"Trades":>7} {"WR%":>6} {"AvgPnL%":>8} {"MDD%":>7}')
for yr in sorted(daily_pnl.index.year.unique()):
    yr_pnl = daily_pnl[daily_pnl.index.year == yr]
    yr_ret = yr_pnl.sum() / CAPITAL * 100
    yr_trades = len(subset[subset['date'].dt.year == yr])
    yr_wr = (subset[subset['date'].dt.year == yr]['pnl'] > 0).mean() * 100
    yr_avg = subset[subset['date'].dt.year == yr]['pnl'].mean() * 100
    yr_mdd = ((yr_pnl.cumsum() - yr_pnl.cumsum().cummax()) / CAPITAL).min() * 100
    print(f'  {yr:<6} {yr_ret:>+8.1f} {yr_trades:>7} {yr_wr:>6.1f} {yr_avg:>8.3f} {yr_mdd:>7.1f}')

# Monthly summary
print(f'\n{"=" * 70}')
print('MONTHLY SUMMARY (all months)')
print(f'{"=" * 70}')
monthly_ret = daily_pnl.resample('ME').sum() / CAPITAL * 100
neg_months = (monthly_ret < 0).sum()
total_months = len(monthly_ret)
print(f'  Positive months: {total_months - neg_months}/{total_months} ({(total_months-neg_months)/total_months*100:.1f}%)')
print(f'  Negative months: {neg_months}')
if neg_months > 0:
    neg = monthly_ret[monthly_ret < 0]
    for idx, val in neg.items():
        print(f'    NEGATIVE: {idx.strftime("%Y-%m")}: {val:.2f}%')

# Rolling returns
print(f'\n{"=" * 70}')
print('ROLLING RETURNS')
print(f'{"=" * 70}')
for period, label in [(63, '3M'), (126, '6M'), (252, '12M')]:
    rolling = daily_ret.rolling(period).apply(lambda x: (1+x).prod() - 1)
    rolling = rolling.dropna()
    print(f'  Rolling {label}: min={rolling.min()*100:.1f}% | max={rolling.max()*100:.1f}% | positive={((rolling>0).mean()*100):.1f}%')

# Position size analysis
print(f'\n{"=" * 70}')
print('POSITION SIZE ANALYSIS')
print(f'{"=" * 70}')
print(f'  Avg position: {subset["actual_pos_pct"].mean()*100:.1f}% = {subset["actual_pos_pct"].mean()*CAPITAL:,.0f}')
print(f'  Max position: {subset["actual_pos_pct"].max()*100:.1f}% = {subset["actual_pos_pct"].max()*CAPITAL:,.0f}')
print(f'  Avg daily exposure: {subset.groupby("date")["actual_pos_pct"].sum().mean()*100:.1f}%')
print(f'  Max daily exposure: {subset.groupby("date")["actual_pos_pct"].sum().max()*100:.1f}%')

# Trades per day distribution
daily_counts = subset.groupby('date').size()
print(f'\n  Trades/day distribution:')
print(f'    1 trade: {(daily_counts==1).sum()} days')
print(f'    2-3 trades: {((daily_counts>=2)&(daily_counts<=3)).sum()} days')
print(f'    4-5 trades: {((daily_counts>=4)&(daily_counts<=5)).sum()} days')
print(f'    6-10 trades: {((daily_counts>=6)&(daily_counts<=10)).sum()} days')
