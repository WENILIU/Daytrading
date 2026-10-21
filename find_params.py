import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

# The previous result: 1299 trades, WR 84.8%, CAGR 1063%, MDD -0.4%
# Let's find what confirm_min gives ~1299 trades with WR ~85%
print("=== Finding parameters that match previous result ===")
print("Target: ~1299 trades, WR ~84.8%, MDD ~-0.4%")
print()

for cm in [0.0, 0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04]:
    subset = data[data['fav_move'] >= cm]
    if len(subset) == 0:
        continue
    wr = (subset['pnl'] > 0).mean() * 100
    avg_pnl = subset['pnl'].mean() * 100
    print(f"  confirm>={cm*100:.1f}%: trades={len(subset)}, WR={wr:.1f}%, avg_pnl={avg_pnl:.3f}%")

# Try with 500万 capital and specific position sizing
print("\n\n=== Simulating with 500万, various configs ===")
capital = 5_000_000

def sim_with_capital(trade_data, confirm_min, base_pct, max_pos, max_exp):
    subset = trade_data[trade_data['fav_move'] >= confirm_min].copy()
    if len(subset) == 0: return None
    subset['pos_pct'] = base_pct
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
            'win_rate': (subset['pnl'] > 0).mean(),
            'daily_avg': daily_pnl.mean(),
            'total_pnl': daily_pnl.sum()}

# The previous result had 1299 trades - let's find what confirm gives that
# and what position sizing gives CAGR 1063%
for cm in [0.02, 0.025, 0.03, 0.035]:
    for bp in [0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10]:
        for mp in [5, 8, 10, 15, 20, 30]:
            for me in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]:
                r = sim_with_capital(data, cm, bp, mp, me)
                if r and abs(r['trades'] - 1299) < 100 and r['win_rate'] > 0.83 and r['mdd'] > -0.006:
                    print(f"  MATCH: cm={cm*100:.1f}% bp={bp*100:.0f}% mp={mp} me={me*100:.0f}%")
                    print(f"    trades={r['trades']} WR={r['win_rate']*100:.1f}% CAGR={r['cagr']*100:.0f}% MDD={r['mdd']*100:.1f}%")
                    print(f"    daily_avg={r['daily_avg']:,.0f} total={r['total_pnl']:,.0f}")
                    print()
