import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

capital = 4_500_000

def sim(trade_data, confirm_min, tiers, base_short, max_pos, max_exp):
    subset = trade_data[trade_data['fav_move'] >= confirm_min].copy()
    subset = subset[subset['direction'] == 'SHORT']  # SHORT only
    if len(subset) == 0: return None
    mult = np.zeros(len(subset))
    for min_move, m in sorted(tiers, reverse=True):
        cond = (subset['fav_move'].values >= min_move) & (mult == 0)
        mult[cond] = m
    subset['multiplier'] = mult
    subset = subset[subset['multiplier'] > 0]
    if len(subset) == 0: return None
    subset['pos_pct'] = base_short * subset['multiplier']
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
            'total_pnl': daily_pnl.sum(), 'days': len(daily_pnl),
            'trades_per_day': len(subset)/len(daily_pnl)}

tiers = [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)]

print("=== SHORT ONLY: Diversification vs Concentration ===\n")

configs = [
    ("集中(目前)", 0.025, 0.08, 10, 0.50),
    ("中等", 0.02, 0.05, 15, 0.50),
    ("分散", 0.015, 0.04, 20, 0.60),
    ("更分散", 0.01, 0.03, 30, 0.70),
    ("極分散", 0.005, 0.025, 30, 0.75),
    ("低門檻大筆", 0.01, 0.04, 30, 0.80),
]

for label, cm, bs, mp, me in configs:
    r = sim(data, cm, tiers, bs, mp, me)
    if r:
        print(f"{label: <8}: cm={cm*100:.1f}% bs={bs*100:.0f}% mp={mp} me={me*100:.0f}%")
        print(f"  WR={r['win_rate']*100:.1f}% CAGR={r['cagr']*100:.0f}% MDD={r['mdd']*100:.1f}% Sharpe={r['sharpe']:.1f}")
        print(f"  trades={r['trades']} days={r['days']} per_day={r['trades_per_day']:.1f} daily_avg={r['daily_avg']:,.0f}")
        print()
