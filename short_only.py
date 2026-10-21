import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

def run_sim(trade_data, confirm_min, tiers, base_short, base_long, max_pos, max_exp, capital=4_500_000):
    subset = trade_data[trade_data['fav_move'] >= confirm_min].copy()
    if len(subset) == 0: return None
    mult = np.zeros(len(subset))
    for min_move, m in sorted(tiers, reverse=True):
        cond = (subset['fav_move'].values >= min_move) & (mult == 0)
        mult[cond] = m
    subset['multiplier'] = mult
    subset = subset[subset['multiplier'] > 0]
    if len(subset) == 0: return None
    subset['pos_pct'] = np.where(subset['direction']=='SHORT', base_short, base_long) * subset['multiplier']
    subset = subset.sort_values(['date', 'fav_move'], ascending=[True, False])
    subset['day_rank'] = subset.groupby('date').cumcount()
    subset = subset[subset['day_rank'] < max_pos]
    subset['cum_exp'] = subset.groupby('date')['pos_pct'].cumsum()
    subset = subset[subset['cum_exp'] <= max_exp]
    if len(subset) == 0: return None
    subset['dollar_pnl'] = subset['pnl'] * subset['pos_pct'] * capital
    daily_pnl = subset.groupby('date')['dollar_pnl'].sum()
    daily_ret = daily_pnl / capital
    cum = (1 + daily_ret).cumprod()
    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
    if years < 0.3 or cum.iloc[-1] <= 0: return None
    cagr = cum.iloc[-1] ** (1/years) - 1
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0
    return {'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe, 'trades': len(subset),
            'win_rate': (subset['pnl'] > 0).mean(), 'daily_avg': daily_pnl.mean(),
            'total_pnl': daily_pnl.sum(), 'daily_pnl': daily_pnl, 'subset': subset}

tiers = [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)]

print("=== COMPARISON: SHORT only vs SHORT+LONG ===\n")

# Config A: SHORT only (no LONG)
print("--- A: SHORT ONLY (confirm=2.5%, bs=8%) ---")
short_data = data[data['direction'] == 'SHORT']
r = run_sim(short_data, 0.025, tiers, 0.08, 0.0, 10, 0.5)
if r:
    print(f"  Trades: {r['trades']}, WR: {r['win_rate']*100:.1f}%")
    print(f"  CAGR: {r['cagr']*100:.0f}%, MDD: {r['mdd']*100:.1f}%, Sharpe: {r['sharpe']:.1f}")
    print(f"  Daily Avg: {r['daily_avg']:,.0f}, Total: {r['total_pnl']:,.0f}")
    print(f"  Trades/day: {r['trades']/len(r['daily_pnl']):.1f}")
    # Annual
    dp = r['daily_pnl']
    for yr in sorted(dp.index.year.unique()):
        yr_ret = dp[dp.index.year==yr].sum() / 4_500_000 * 100
        print(f"    {yr}: {yr_ret:+.0f}%")

# Config B: SHORT + LONG with low LONG confirm
print("\n--- B: SHORT(confirm=2.5%) + LONG(confirm=0.5%) ---")
# Separate handling
short_sub = data[(data['direction']=='SHORT') & (data['fav_move'] >= 0.025)].copy()
long_sub = data[(data['direction']=='LONG') & (data['fav_move'] >= 0.005)].copy()
combined = pd.concat([short_sub, long_sub])
r2 = run_sim(combined, 0.0, tiers, 0.08, 0.015, 10, 0.5)
if r2:
    print(f"  Trades: {r2['trades']}, WR: {r2['win_rate']*100:.1f}%")
    print(f"  CAGR: {r2['cagr']*100:.0f}%, MDD: {r2['mdd']*100:.1f}%, Sharpe: {r2['sharpe']:.1f}")
    print(f"  Daily Avg: {r2['daily_avg']:,.0f}, Total: {r2['total_pnl']:,.0f}")
    print(f"  Trades/day: {r2['trades']/len(r2['daily_pnl']):.1f}")
    dp = r2['daily_pnl']
    for yr in sorted(dp.index.year.unique()):
        yr_ret = dp[dp.index.year==yr].sum() / 4_500_000 * 100
        print(f"    {yr}: {yr_ret:+.0f}%")

# Config C: SHORT only, higher position
print("\n--- C: SHORT ONLY (confirm=2.5%, bs=10%, me=60%) ---")
r3 = run_sim(short_data, 0.025, tiers, 0.10, 0.0, 10, 0.6)
if r3:
    print(f"  Trades: {r3['trades']}, WR: {r3['win_rate']*100:.1f}%")
    print(f"  CAGR: {r3['cagr']*100:.0f}%, MDD: {r3['mdd']*100:.1f}%, Sharpe: {r3['sharpe']:.1f}")
    print(f"  Daily Avg: {r3['daily_avg']:,.0f}, Total: {r3['total_pnl']:,.0f}")
    print(f"  Trades/day: {r3['trades']/len(r3['daily_pnl']):.1f}")
    dp = r3['daily_pnl']
    for yr in sorted(dp.index.year.unique()):
        yr_ret = dp[dp.index.year==yr].sum() / 4_500_000 * 100
        print(f"    {yr}: {yr_ret:+.0f}%")

# Config D: SHORT only, confirm=3% (even higher WR)
print("\n--- D: SHORT ONLY (confirm=3%, bs=8%) ---")
r4 = run_sim(short_data, 0.03, tiers, 0.08, 0.0, 10, 0.5)
if r4:
    print(f"  Trades: {r4['trades']}, WR: {r4['win_rate']*100:.1f}%")
    print(f"  CAGR: {r4['cagr']*100:.0f}%, MDD: {r4['mdd']*100:.1f}%, Sharpe: {r4['sharpe']:.1f}")
    print(f"  Daily Avg: {r4['daily_avg']:,.0f}, Total: {r4['total_pnl']:,.0f}")
    print(f"  Trades/day: {r4['trades']/len(r4['daily_pnl']):.1f}")
    dp = r4['daily_pnl']
    for yr in sorted(dp.index.year.unique()):
        yr_ret = dp[dp.index.year==yr].sum() / 4_500_000 * 100
        print(f"    {yr}: {yr_ret:+.0f}%")
