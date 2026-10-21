import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

capital = 4_500_000
tiers = [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)]

def sim_short_long(short_confirm, short_bs, long_confirm, long_bs, max_pos=10, max_exp=0.50):
    """Simulate with separate SHORT and LONG parameters"""
    shorts = data[(data['direction']=='SHORT') & (data['fav_move'] >= short_confirm)].copy()
    longs = data[(data['direction']=='LONG') & (data['fav_move'] >= long_confirm)].copy()
    
    combined = pd.concat([shorts, longs])
    if len(combined) == 0: return None
    
    # Assign tier multiplier
    mult = np.zeros(len(combined))
    for min_move, m in sorted(tiers, reverse=True):
        cond = (combined['fav_move'].values >= min_move) & (mult == 0)
        mult[cond] = m
    combined['multiplier'] = mult
    combined = combined[combined['multiplier'] > 0]
    if len(combined) == 0: return None
    
    combined['pos_pct'] = np.where(combined['direction']=='SHORT', short_bs, long_bs) * combined['multiplier']
    combined = combined.sort_values(['date', 'fav_move'], ascending=[True, False])
    combined['day_rank'] = combined.groupby('date').cumcount()
    combined = combined[combined['day_rank'] < max_pos]
    combined['cum_exp'] = combined.groupby('date')['pos_pct'].cumsum()
    combined = combined[combined['cum_exp'] <= max_exp]
    if len(combined) == 0: return None
    
    combined['dollar_pnl'] = combined['pnl'] * combined['pos_pct'] * capital
    daily_pnl = combined.groupby('date')['dollar_pnl'].sum()
    daily_ret = daily_pnl / capital
    cum = (1 + daily_ret).cumprod()
    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
    if years < 0.3 or cum.iloc[-1] <= 0: return None
    cagr = cum.iloc[-1] ** (1/years) - 1
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0
    
    # Check overlap: do LONG and SHORT occur on same days?
    short_days = set(shorts['date'].unique())
    long_days = set(longs['date'].unique())
    overlap = len(short_days & long_days)
    
    return {'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe, 'trades': len(combined),
            'win_rate': (combined['pnl'] > 0).mean(), 'daily_avg': daily_pnl.mean(),
            'total_pnl': daily_pnl.sum(), 'days': len(daily_pnl),
            'short_trades': len(shorts), 'long_trades': len(longs),
            'overlap_days': overlap, 'short_days': len(short_days), 'long_days': len(long_days)}

print("=== SHORT ONLY baseline ===")
base = sim_short_long(0.025, 0.08, 999, 0)  # no LONG
if base:
    print(f"  WR={base['win_rate']*100:.1f}% CAGR={base['cagr']*100:.0f}% MDD={base['mdd']*100:.1f}% Sharpe={base['sharpe']:.1f}")
    print(f"  trades={base['trades']} days={base['days']}")

print("\n\n=== Adding LONG with various confirm thresholds ===")
print(f"{'LONG confirm':<14} {'LONG size':<10} {'WR':<7} {'CAGR':<8} {'MDD':<7} {'Sharpe':<8} {'L trades':<9} {'Overlap days'}")
print("-" * 90)

for lc in [-0.05, -0.02, 0.0, 0.005, 0.01, 0.015, 0.02, 0.025]:
    for lb in [0.01, 0.02, 0.03, 0.04]:
        r = sim_short_long(0.025, 0.08, lc, lb)
        if r and r['long_trades'] > 10:
            marker = " <-- BETTER MDD" if r['mdd'] > base['mdd'] else ""
            marker2 = " <-- BETTER CAGR" if r['cagr'] > base['cagr'] else ""
            print(f"  {lc*100:+.1f}%{'':<8} {lb*100:.0f}%{'':<6} {r['win_rate']*100:.1f}%  {r['cagr']*100:.0f}%{'':<4} {r['mdd']*100:.1f}%{'':<3} {r['sharpe']:<8.1f} {r['long_trades']:<9} {r['overlap_days']}/{r['short_days']}{marker}{marker2}")

# Check: are LONG signals on DIFFERENT days (diversification)?
print("\n\n=== Day overlap analysis ===")
shorts = data[(data['direction']=='SHORT') & (data['fav_move'] >= 0.025)]
longs_all = data[(data['direction']=='LONG')]
short_days = set(shorts['date'].unique())
long_days_all = set(longs_all['date'].unique())
print(f"SHORT signal days: {len(short_days)}")
print(f"LONG signal days (all): {len(long_days_all)}")
print(f"Overlap: {len(short_days & long_days_all)} ({len(short_days & long_days_all)/len(short_days)*100:.0f}% of SHORT days)")
print(f"LONG-only days: {len(long_days_all - short_days)}")

# What happens on LONG-only days?
long_only_days = long_days_all - short_days
long_only_signals = longs_all[longs_all['date'].isin(long_only_days)]
print(f"\nLONG-only signals: {len(long_only_signals)}")
print(f"  WR: {(long_only_signals['pnl']>0).mean()*100:.1f}%")
print(f"  Avg PnL: {long_only_signals['pnl'].mean()*100:.3f}%")
