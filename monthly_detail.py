import pickle, pandas as pd, numpy as np
from finlab import data as fdata
import warnings
warnings.filterwarnings('ignore')

strat_data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
strat_data['date'] = pd.to_datetime(strat_data['date'])
strat_data['fav_move'] = np.where(strat_data['direction']=='SHORT', -strat_data['early_move_15'], strat_data['early_move_15'])

CAPITAL = 4_500_000
CONFIRM_MIN = 0.025
BASE_SHORT = 0.08
MAX_POS = 10
MAX_EXP = 0.50
MIN_PRICE = 30
MAX_PRICE = 225
TIERS = [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)]
COST = 0.0017

subset = strat_data[(strat_data['direction']=='SHORT') & (strat_data['fav_move'] >= CONFIRM_MIN) &
                    (strat_data['entry'] >= MIN_PRICE) & (strat_data['entry'] <= MAX_PRICE)].copy()

try:
    disposal = fdata.get('etl:disposal_stock_filter', start='20230501', end='20231231')
    def is_disp(row):
        if row['date'] in disposal.index and row['stock'] in disposal.columns:
            return not bool(disposal.loc[row['date'], row['stock']])
        return False
    subset = subset[~subset.apply(is_disp, axis=1)]
except:
    pass

mult = np.zeros(len(subset))
for min_move, m in sorted(TIERS, reverse=True):
    cond = (subset['fav_move'].values >= min_move) & (mult == 0)
    mult[cond] = m
subset['multiplier'] = mult
subset = subset[subset['multiplier'] > 0]
subset['pos_pct'] = BASE_SHORT * subset['multiplier']
subset['shares'] = np.floor(subset['pos_pct'] * CAPITAL / subset['entry'] / 1000).astype(int) * 1000
subset = subset[subset['shares'] >= 1000]
subset['actual_pos_pct'] = (subset['shares'] * subset['entry']) / CAPITAL

subset = subset.sort_values(['date', 'fav_move'], ascending=[True, False])
subset['day_rank'] = subset.groupby('date').cumcount()
subset = subset[subset['day_rank'] < MAX_POS]
subset['cum_exp'] = subset.groupby('date')['actual_pos_pct'].cumsum()
subset = subset[subset['cum_exp'] <= MAX_EXP]

subset['pnl_net'] = subset['pnl'] - COST
subset['dollar_pnl'] = subset['pnl_net'] * subset['actual_pos_pct'] * CAPITAL

# Monthly summary
print(f"{'Month':<10} {'Trades':>6} {'WR':>6} {'PnL':>12} {'Ret%':>7} {'Avg/Trade':>10} {'Max Pos':>8}")
print("-" * 70)

monthly = subset.groupby(subset['date'].dt.to_period('M')).agg(
    trades=('pnl_net', 'count'),
    wins=('pnl_net', lambda x: (x > 0).sum()),
    total_pnl=('dollar_pnl', 'sum'),
    avg_pnl=('pnl_net', 'mean'),
    max_pos=('actual_pos_pct', 'max'),
)

cum_ret = 0
for period, row in monthly.iterrows():
    wr = row['wins'] / row['trades'] * 100 if row['trades'] > 0 else 0
    ret = row['total_pnl'] / CAPITAL * 100
    cum_ret = (1 + cum_ret/100) * (1 + ret/100) * 100 - 1
    bar = "+" * int(max(0, ret/3))
    print(f"{str(period):<10} {int(row['trades']):>6} {wr:>5.0f}% {row['total_pnl']:>+12,.0f} {ret:>+6.1f}% {row['avg_pnl']*100:>+9.2f}% {row['max_pos']*100:>7.1f}%")

# Summary
total_pnl = subset['dollar_pnl'].sum()
total_trades = len(subset)
total_wr = (subset['pnl_net'] > 0).mean() * 100
print("-" * 70)
print(f"{'TOTAL':<10} {total_trades:>6} {total_wr:>5.1f}% {total_pnl:>+12,.0f}")

# Cumulative
daily_pnl = subset.groupby('date')['dollar_pnl'].sum()
daily_ret = daily_pnl / CAPITAL
cum = (1 + daily_ret).cumprod()
years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
cagr = cum.iloc[-1] ** (1/years) - 1
mdd = ((cum - cum.cummax()) / cum.cummax()).min()
print(f"\nCAGR: {cagr*100:.0f}% | MDD: {mdd*100:.1f}% | Total: {total_pnl:,.0f}")
