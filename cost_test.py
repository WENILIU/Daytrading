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
COST = 0.0017  # 0.17% per trade

# Filter
subset = strat_data[(strat_data['direction']=='SHORT') & (strat_data['fav_move'] >= CONFIRM_MIN) &
                    (strat_data['entry'] >= MIN_PRICE) & (strat_data['entry'] <= MAX_PRICE)].copy()

# Disposal
try:
    disposal = fdata.get('etl:disposal_stock_filter', start='20230501', end='20231231')
    def is_disp(row):
        if row['date'] in disposal.index and row['stock'] in disposal.columns:
            return not bool(disposal.loc[row['date'], row['stock']])
        return False
    subset = subset[~subset.apply(is_disp, axis=1)]
except:
    pass

# Tier + 整張
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

# Daily limits
subset = subset.sort_values(['date', 'fav_move'], ascending=[True, False])
subset['day_rank'] = subset.groupby('date').cumcount()
subset = subset[subset['day_rank'] < MAX_POS]
subset['cum_exp'] = subset.groupby('date')['actual_pos_pct'].cumsum()
subset = subset[subset['cum_exp'] <= MAX_EXP]

# Apply cost: subtract COST from each trade's pnl
subset['pnl_net'] = subset['pnl'] - COST

# Compare: with and without cost
print(f"{'='*60}")
print(f"COMPARISON: Cost 0% vs 0.17%")
print(f"{'='*60}")
print(f"Trades: {len(subset)}")
print(f"Avg gross PnL: {subset['pnl'].mean()*100:.3f}%")
print(f"Avg net PnL (after 0.17%): {subset['pnl_net'].mean()*100:.3f}%")
print(f"WR gross: {(subset['pnl']>0).mean()*100:.1f}%")
print(f"WR net: {(subset['pnl_net']>0).mean()*100:.1f}%")

def calc_metrics(pnl_col):
    subset['_pnl_use'] = subset[pnl_col]
    subset['dollar_pnl'] = subset['_pnl_use'] * subset['actual_pos_pct'] * CAPITAL
    daily_pnl = subset.groupby('date')['dollar_pnl'].sum()
    daily_ret = daily_pnl / CAPITAL
    cum = (1 + daily_ret).cumprod()
    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
    cagr = cum.iloc[-1] ** (1/years) - 1
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
    return {'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe, 'daily_avg': daily_pnl.mean(),
            'total': daily_pnl.sum(), 'daily_pnl': daily_pnl}

print(f"\n{'='*60}")
print("WITHOUT COST (gross)")
print(f"{'='*60}")
r0 = calc_metrics('pnl')
print(f"  CAGR: {r0['cagr']*100:.0f}% | MDD: {r0['mdd']*100:.1f}% | Sharpe: {r0['sharpe']:.1f}")
print(f"  Daily: {r0['daily_avg']:,.0f} | Total: {r0['total']:,.0f}")

print(f"\n{'='*60}")
print("WITH COST 0.17%")
print(f"{'='*60}")
r1 = calc_metrics('pnl_net')
print(f"  CAGR: {r1['cagr']*100:.0f}% | MDD: {r1['mdd']*100:.1f}% | Sharpe: {r1['sharpe']:.1f}")
print(f"  Daily: {r1['daily_avg']:,.0f} | Total: {r1['total']:,.0f}")

print(f"\n{'='*60}")
print("WITH COST 0.23% (previous)")
print(f"{'='*60}")
subset['pnl_023'] = subset['pnl'] - 0.0023
r2 = calc_metrics('pnl_023')
print(f"  CAGR: {r2['cagr']*100:.0f}% | MDD: {r2['mdd']*100:.1f}% | Sharpe: {r2['sharpe']:.1f}")
print(f"  Daily: {r2['daily_avg']:,.0f} | Total: {r2['total']:,.0f}")

# Annual with 0.17% cost
print(f"\n{'='*60}")
print("ANNUAL (cost 0.17%)")
print(f"{'='*60}")
dp = r1['daily_pnl']
for yr in sorted(dp.index.year.unique()):
    yr_pnl = dp[dp.index.year == yr]
    yr_ret = yr_pnl.sum() / CAPITAL * 100
    yr_trades = len(subset[subset['date'].dt.year == yr])
    yr_wr = (subset[subset['date'].dt.year == yr]['pnl_net'] > 0).mean() * 100
    print(f"  {yr}: {yr_ret:+6.0f}% | WR={yr_wr:.0f}% | trades={yr_trades}")
