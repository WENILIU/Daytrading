import pickle, pandas as pd, numpy as np

data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])

def assign_tier(row):
    move = row['early_move_15']
    if row['direction'] == 'SHORT':
        drop = -move
    else:
        drop = move
    if drop > 0.03: return 'T5(>3%)'
    elif drop > 0.015: return 'T4(1.5-3%)'
    elif drop > 0.005: return 'T3(0.5-1.5%)'
    elif drop > 0.0: return 'T2(0-0.5%)'
    else: return 'SKIP(<=0%)'

data['tier'] = data.apply(assign_tier, axis=1)

print('=== Tier Performance ===')
tier_stats = data.groupby('tier').agg(
    count=('pnl', 'count'),
    win_rate=('pnl', lambda x: (x>0).mean()*100),
    avg_pnl=('pnl', 'mean'),
    total_pnl=('pnl', 'sum')
).sort_index()
print(tier_stats.round(4))

confirmed = data[data['tier'] != 'SKIP(<=0%)']
print(f'\n=== Confirmed only (T2-T5) ===')
print(f'Trades: {len(confirmed)}')
wr = (confirmed['pnl']>0).mean()*100
print(f'Win rate: {wr:.1f}%')
print(f'Avg PnL: {confirmed["pnl"].mean()*100:.3f}%')

daily = confirmed.groupby('date')['pnl'].agg(['count', 'mean', 'sum'])
print(f'\nAvg trades/day (confirmed): {daily["count"].mean():.1f}')
print(f'Max trades/day: {daily["count"].max()}')
print(f'Days with trades: {len(daily)}')

# Simulate with tiered sizing
print('\n=== Simulated with tiered sizing ===')
capital = 4_500_000
tier_mult = {'T5(>3%)': 2.0, 'T4(1.5-3%)': 1.5, 'T3(0.5-1.5%)': 1.0, 'T2(0-0.5%)': 0.5}
base_short = 0.05  # 5% base for short
base_long = 0.025  # 2.5% base for long

confirmed = confirmed.copy()
confirmed['position_pct'] = confirmed.apply(
    lambda r: (base_short if r['direction']=='SHORT' else base_long) * tier_mult.get(r['tier'], 0), axis=1)
confirmed['dollar_pnl'] = confirmed['pnl'] * confirmed['position_pct'] * capital

daily_pnl = confirmed.groupby('date')['dollar_pnl'].sum()
daily_ret = daily_pnl / capital
cum = (1 + daily_ret).cumprod()
years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
cagr = cum.iloc[-1] ** (1/years) - 1
mdd = ((cum - cum.cummax()) / cum.cummax()).min()

print(f'Period: {daily_ret.index[0].date()} to {daily_ret.index[-1].date()}')
print(f'CAGR: {cagr*100:.1f}%')
print(f'MDD: {mdd*100:.1f}%')
print(f'Total trades: {len(confirmed)}')
