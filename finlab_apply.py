from finlab import data
import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

# Get disposal stock data (free until 2023-12-31)
print("Downloading disposal stock data...")
disposal = data.get('etl:disposal_stock_filter', start='20230501', end='20231231')
print(f"Shape: {disposal.shape}")
print(f"Date range: {disposal.index.min()} to {disposal.index.max()}")

# Check: True means IS disposal (cannot trade)?
# Count True per day
true_counts = disposal.sum(axis=1)
print(f"\nDisposal stocks per day: min={true_counts.min()}, max={true_counts.max()}, mean={true_counts.mean():.0f}")
print(f"Sample (2023-10-01): {true_counts.get('2023-10-02', 'N/A')}")

# Get the actual disposal stocks for a specific day
sample_date = disposal.index[len(disposal.index)//2]
disposal_that_day = disposal.loc[sample_date]
disposal_stocks = disposal_that_day[disposal_that_day].index.tolist()
print(f"\n{sample_date.date()}: {len(disposal_stocks)} disposal stocks")
print(f"Sample: {disposal_stocks[:20]}")

# Now apply to our backtest
print("\n\n=== Applying disposal filter to backtest ===")
strat_data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
strat_data['date'] = pd.to_datetime(strat_data['date'])
strat_data['fav_move'] = np.where(strat_data['direction']=='SHORT', -strat_data['early_move_15'], strat_data['early_move_15'])

# Our signals
subset = strat_data[(strat_data['direction']=='SHORT') & (strat_data['fav_move'] >= 0.025) & 
                    (strat_data['entry'] >= 30) & (strat_data['entry'] <= 225)].copy()

# Check which signals are on disposal days
def is_disposal(row):
    date = row['date']
    stock = row['stock']
    if date in disposal.index and stock in disposal.columns:
        return bool(disposal.loc[date, stock])
    return False  # Unknown = assume not disposal

subset['is_disposal'] = subset.apply(is_disposal, axis=1)
print(f"Signals in disposal period: {subset['is_disposal'].sum()} / {len(subset)} ({subset['is_disposal'].mean()*100:.1f}%)")

# Compare performance
disposal_sigs = subset[subset['is_disposal']]
clean_sigs = subset[~subset['is_disposal']]

if len(disposal_sigs) > 0:
    print(f"\nDisposal signals: {len(disposal_sigs)}, WR={(disposal_sigs['pnl']>0).mean()*100:.1f}%, avg_pnl={disposal_sigs['pnl'].mean()*100:.2f}%")
print(f"Clean signals: {len(clean_sigs)}, WR={(clean_sigs['pnl']>0).mean()*100:.1f}%, avg_pnl={clean_sigs['pnl'].mean()*100:.2f}%")

# Simulate without disposal
tiers = [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)]
capital = 4_500_000

def run_sim(trade_data):
    if len(trade_data) == 0: return None
    mult = np.zeros(len(trade_data))
    for min_move, m in sorted(tiers, reverse=True):
        cond = (trade_data['fav_move'].values >= min_move) & (mult == 0)
        mult[cond] = m
    td = trade_data.copy()
    td['multiplier'] = mult
    td = td[td['multiplier'] > 0]
    if len(td) == 0: return None
    td['pos_pct'] = 0.08 * td['multiplier']
    td['shares'] = np.floor(td['pos_pct'] * capital / td['entry'] / 1000).astype(int) * 1000
    td = td[td['shares'] >= 1000]
    td['actual_pos_pct'] = (td['shares'] * td['entry']) / capital
    td = td.sort_values(['date', 'fav_move'], ascending=[True, False])
    td['day_rank'] = td.groupby('date').cumcount()
    td = td[td['day_rank'] < 10]
    td['cum_exp'] = td.groupby('date')['actual_pos_pct'].cumsum()
    td = td[td['cum_exp'] <= 0.50]
    if len(td) == 0: return None
    td['dollar_pnl'] = td['pnl'] * td['actual_pos_pct'] * capital
    daily_pnl = td.groupby('date')['dollar_pnl'].sum()
    daily_ret = daily_pnl / capital
    cum = (1 + daily_ret).cumprod()
    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
    cagr = cum.iloc[-1] ** (1/years) - 1
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
    return {'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe, 'trades': len(td),
            'win_rate': (td['pnl'] > 0).mean(), 'daily_avg': daily_pnl.mean()}

print("\n=== WITH disposal stocks ===")
r1 = run_sim(subset)
if r1: print(f"  WR={r1['win_rate']*100:.1f}% CAGR={r1['cagr']*100:.0f}% MDD={r1['mdd']*100:.1f}% trades={r1['trades']}")

print("\n=== WITHOUT disposal stocks ===")
r2 = run_sim(clean_sigs)
if r2: print(f"  WR={r2['win_rate']*100:.1f}% CAGR={r2['cagr']*100:.0f}% MDD={r2['mdd']*100:.1f}% trades={r2['trades']}")
