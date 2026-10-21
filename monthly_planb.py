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
MAX_POS = 15
MAX_EXP = 0.70
COST = 0.0017
BASE_POS = 0.05
HIGH_MULT = 1.5

# SHORT
short = sig[sig['direction'] == 'SHORT'].copy()
short = short[short['adj_gap'] >= GAP_THRESHOLD]
short = short[(short['entry'] >= MIN_PRICE) & (short['entry'] <= MAX_PRICE)]
sl_hit = short['day_high'] >= short['entry'] * (1 + SL_PCT)
tp_hit = short['day_low'] <= short['entry'] * (1 - TP_PCT)
short['pnl'] = np.where(tp_hit, TP_PCT, np.where(sl_hit, -SL_PCT, (short['entry'] - short['day_close']) / short['entry'])) - COST

# LONG
long = sig[sig['direction'] == 'LONG'].copy()
long = long[long['adj_gap'] <= -GAP_THRESHOLD]
long = long[(long['entry'] >= MIN_PRICE) & (long['entry'] <= MAX_PRICE)]
sl_hit_l = long['day_low'] <= long['entry'] * (1 - SL_PCT)
tp_hit_l = long['day_high'] >= long['entry'] * (1 + TP_PCT)
long['pnl'] = np.where(tp_hit_l, TP_PCT, np.where(sl_hit_l, -SL_PCT, (long['day_close'] - long['entry']) / long['entry'])) - COST

combined = pd.concat([short, long], ignore_index=True)
combined['_abs_gap'] = combined['adj_gap'].abs()

# Position sizing
combined['pos_pct'] = np.where(combined['_abs_gap'] > 0.07, BASE_POS * HIGH_MULT, BASE_POS)
combined['shares'] = np.floor(combined['pos_pct'] * CAPITAL / combined['entry'] / 1000).astype(int) * 1000
combined = combined[combined['shares'] >= 1000]
combined['actual_pos'] = (combined['shares'] * combined['entry']) / CAPITAL

# Daily limits
combined = combined.sort_values(['date', '_abs_gap'], ascending=[True, False])
combined['day_rank'] = combined.groupby('date').cumcount()
combined = combined[combined['day_rank'] < MAX_POS]
combined['cum_exp'] = combined.groupby('date')['actual_pos'].cumsum()
combined = combined[combined['cum_exp'] <= MAX_EXP]

# PnL
combined['dollar_pnl'] = combined['pnl'] * combined['actual_pos'] * CAPITAL
daily_pnl = combined.groupby('date')['dollar_pnl'].sum()
daily_ret = daily_pnl / CAPITAL

# Monthly
monthly_pnl = daily_pnl.resample('ME').sum()
monthly_ret = monthly_pnl / CAPITAL * 100
monthly_trades = combined.groupby(combined['date'].dt.to_period('M')).size()

print('=' * 80)
print('MONTHLY PERFORMANCE — Plan B (CAGR~108%, MDD~-1.7%)')
print('=' * 80)
print(f'  {"Year":<6} {"Jan":>6} {"Feb":>6} {"Mar":>6} {"Apr":>6} {"May":>6} {"Jun":>6} {"Jul":>6} {"Aug":>6} {"Sep":>6} {"Oct":>6} {"Nov":>6} {"Dec":>6} {"Year":>8}')
print(f'  {"-"*6} {"-"*6} {"-"*6} {"-"*6} {"-"*6} {"-"*6} {"-"*6} {"-"*6} {"-"*6} {"-"*6} {"-"*6} {"-"*6} {"-"*6} {"-"*8}')

for yr in sorted(monthly_ret.index.year.unique()):
    row = []
    yr_total = 0
    for m in range(1, 13):
        try:
            period = pd.Period(year=yr, month=m, freq='M')
            val = monthly_ret.get(pd.Timestamp(year=yr, month=m, day=1) + pd.offsets.MonthEnd(0), None)
            if val is None:
                # Try to find it
                mask = (monthly_ret.index.year == yr) & (monthly_ret.index.month == m)
                if mask.any():
                    val = monthly_ret[mask].iloc[0]
                else:
                    val = None
            if val is not None and not np.isnan(val):
                row.append(f'{val:>+6.1f}')
                yr_total += val
            else:
                row.append('     -')
        except:
            row.append('     -')
    print(f'  {yr:<6} {" ".join(row)} {yr_total:>+8.1f}')

# Summary stats
print(f'\n{"=" * 80}')
print('SUMMARY')
print(f'{"=" * 80}')
total_months = len(monthly_ret)
pos_months = (monthly_ret > 0).sum()
neg_months = (monthly_ret < 0).sum()
print(f'  Total months: {total_months}')
print(f'  Positive: {pos_months} ({pos_months/total_months*100:.1f}%)')
print(f'  Negative: {neg_months}')
if neg_months > 0:
    for idx, val in monthly_ret[monthly_ret < 0].items():
        print(f'    NEGATIVE: {idx.strftime("%Y-%m")}: {val:.2f}%')
print(f'  Best month: {monthly_ret.max():+.1f}% ({monthly_ret.idxmax().strftime("%Y-%m")})')
print(f'  Worst month: {monthly_ret.min():+.1f}% ({monthly_ret.idxmin().strftime("%Y-%m")})')
print(f'  Avg monthly: {monthly_ret.mean():+.2f}%')
print(f'  Median monthly: {monthly_ret.median():+.2f}%')

# Cumulative
cum = (1 + daily_ret).cumprod()
years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
cagr = cum.iloc[-1] ** (1/years) - 1
mdd = ((cum - cum.cummax()) / cum.cummax()).min()
sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
print(f'\n  CAGR: {cagr*100:.1f}%')
print(f'  MDD: {mdd*100:.1f}%')
print(f'  Sharpe: {sharpe:.1f}')
print(f'  Final capital: {CAPITAL * cum.iloc[-1]:,.0f}')
