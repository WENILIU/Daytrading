import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

# Filter SHORT only, confirm >= 2.5%
subset = data[(data['direction']=='SHORT') & (data['fav_move'] >= 0.025)].copy()
tiers = [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)]

mult = np.zeros(len(subset))
for min_move, m in sorted(tiers, reverse=True):
    cond = (subset['fav_move'].values >= min_move) & (mult == 0)
    mult[cond] = m
subset['multiplier'] = mult
subset = subset[subset['multiplier'] > 0]

print(f"Available SHORT signals (confirm>=2.5%): {len(subset)}")
print(f"Price range: {subset['entry'].min():.0f} - {subset['entry'].max():.0f}")
print()

# Simulate with different capitals, checking 整張 impact
def sim_with_zhang(capital, base_pct=0.08, max_pos=10, max_exp=0.50):
    sub = subset.copy()
    sub['pos_pct'] = base_pct * sub['multiplier']
    sub['target_value'] = sub['pos_pct'] * capital
    
    # 整張 constraint: shares = floor(target_value / price / 1000) * 1000
    sub['shares'] = np.floor(sub['target_value'] / sub['entry'] / 1000).astype(int) * 1000
    sub['actual_value'] = sub['shares'] * sub['entry']
    sub['actual_pos_pct'] = sub['actual_value'] / capital
    
    # Filter: must be >= 1 zhang
    sub = sub[sub['shares'] >= 1000]
    
    # Daily limits
    sub = sub.sort_values(['date', 'fav_move'], ascending=[True, False])
    sub['day_rank'] = sub.groupby('date').cumcount()
    sub = sub[sub['day_rank'] < max_pos]
    sub['cum_exp'] = sub.groupby('date')['actual_pos_pct'].cumsum()
    sub = sub[sub['cum_exp'] <= max_exp]
    
    if len(sub) == 0: return None
    
    sub['dollar_pnl'] = sub['pnl'] * sub['actual_pos_pct'] * capital
    daily_pnl = sub.groupby('date')['dollar_pnl'].sum()
    daily_ret = daily_pnl / capital
    cum = (1 + daily_ret).cumprod()
    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
    cagr = cum.iloc[-1] ** (1/years) - 1
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0
    
    return {'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe, 'trades': len(sub),
            'win_rate': (sub['pnl'] > 0).mean(), 'daily_avg': daily_pnl.mean(),
            'total_pnl': daily_pnl.sum(), 'days': len(daily_pnl),
            'skipped': len(subset) - len(sub)}

# Compare capitals
print("=== Impact of Capital on Performance (same % params) ===")
print(f"{'Capital':<12} {'Trades':<8} {'WR':<7} {'CAGR':<8} {'MDD':<7} {'Sharpe':<8} {'Daily':<10} {'Skipped'}")
print("-" * 85)

for capital in [3_000_000, 4_500_000, 5_000_000, 10_000_000, 20_000_000, 50_000_000]:
    r = sim_with_zhang(capital)
    if r:
        print(f"{capital/10000:.0f}萬{'':<6} {r['trades']:<8} {r['win_rate']*100:.1f}%  {r['cagr']*100:.0f}%{'':<4} {r['mdd']*100:.1f}%{'':<3} {r['sharpe']:<8.1f} {r['daily_avg']:>10,.0f} {r['skipped']}")

# Also test: with 1000萬, can we increase position %?
print("\n\n=== With 1000萬: Optimal position sizing ===")
for bs in [0.05, 0.06, 0.08, 0.10, 0.12, 0.15]:
    r = sim_with_zhang(10_000_000, base_pct=bs)
    if r:
        print(f"  bs={bs*100:.0f}%: WR={r['win_rate']*100:.1f}% CAGR={r['cagr']*100:.0f}% MDD={r['mdd']*100:.1f}% Sharpe={r['sharpe']:.1f} daily={r['daily_avg']:,.0f} trades={r['trades']}")

# Check: what % of signals are skipped due to 整張 at different capitals?
print("\n\n=== 整張 skip rate by capital ===")
for capital in [3_000_000, 4_500_000, 5_000_000, 10_000_000, 20_000_000]:
    sub = subset.copy()
    sub['pos_pct'] = 0.08 * sub['multiplier']
    sub['target_value'] = sub['pos_pct'] * capital
    sub['shares'] = np.floor(sub['target_value'] / sub['entry'] / 1000).astype(int) * 1000
    skipped = (sub['shares'] < 1000).sum()
    print(f"  {capital/10000:.0f}萬: {skipped}/{len(sub)} skipped ({skipped/len(sub)*100:.1f}%) - max price tradeable: {capital*0.08*3/1000:.0f}元(T5)")
