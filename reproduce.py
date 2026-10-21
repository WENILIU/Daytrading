import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

# Target: 1299 trades, WR 84.8%, CAGR 1063%, MDD -0.4%, daily_avg 50919, total 952萬
# Capital: 500萬
# Let me try various configs to match

def sim(trade_data, confirm_min, tiers, base_short, base_long, max_pos, max_exp, capital):
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
            'total_pnl': daily_pnl.sum(), 'days': len(daily_pnl)}

capital = 5_000_000
tiers = [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)]

print("Searching for params matching: 1299 trades, WR 84.8%, CAGR 1063%, MDD -0.4%")
print(f"Target: daily_avg=50,919, total=9,520,000")
print()

best_match = None
best_score = 999

for cm in [0.01, 0.015, 0.02, 0.025]:
    for bs in [0.04, 0.05, 0.06, 0.07, 0.08]:
        for bl in [0.02, 0.025, 0.03, 0.04]:
            for mp in [8, 10, 15, 20, 30]:
                for me in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
                    r = sim(data, cm, tiers, bs, bl, mp, me, capital)
                    if r is None:
                        continue
                    # Score: how close to target
                    score = 0
                    score += abs(r['trades'] - 1299) / 1299
                    score += abs(r['win_rate'] - 0.848) / 0.848
                    score += abs(r['mdd'] - (-0.004)) / 0.004
                    score += abs(r['daily_avg'] - 50919) / 50919
                    
                    if score < best_score:
                        best_score = score
                        best_match = (cm, bs, bl, mp, me, r)

if best_match:
    cm, bs, bl, mp, me, r = best_match
    print(f"BEST MATCH (score={best_score:.3f}):")
    print(f"  confirm={cm*100:.1f}% bs={bs*100:.0f}% bl={bl*100:.1f}% mp={mp} me={me*100:.0f}%")
    print(f"  trades={r['trades']} WR={r['win_rate']*100:.1f}% CAGR={r['cagr']*100:.0f}% MDD={r['mdd']*100:.1f}%")
    print(f"  daily_avg={r['daily_avg']:,.0f} total={r['total_pnl']:,.0f} days={r['days']}")
    print(f"  trades/day={r['trades']/r['days']:.1f}")

# Also try the exact original v3 config (from gap_fade_module.py)
print("\n\n=== Original v3 config (5% gap, 5%/5% SL/TP, 30 pos, 3%/1.5%) ===")
r2 = sim(data, 0.0, [(0.03, 2.0), (0.015, 1.5), (0.005, 1.0), (0.0, 0.5)], 
         0.03, 0.015, 30, 0.7, capital)
if r2:
    print(f"  trades={r2['trades']} WR={r2['win_rate']*100:.1f}% CAGR={r2['cagr']*100:.0f}% MDD={r2['mdd']*100:.1f}%")
    print(f"  daily_avg={r2['daily_avg']:,.0f} total={r2['total_pnl']:,.0f}")

# Try with no tier (flat position)
print("\n=== Flat 6% position, confirm=2%, both directions ===")
r3 = sim(data, 0.02, [(0.0, 1.0)], 0.06, 0.06, 30, 1.0, capital)
if r3:
    print(f"  trades={r3['trades']} WR={r3['win_rate']*100:.1f}% CAGR={r3['cagr']*100:.0f}% MDD={r3['mdd']*100:.1f}%")
    print(f"  daily_avg={r3['daily_avg']:,.0f} total={r3['total_pnl']:,.0f} days={r3['days']}")
    print(f"  trades/day={r3['trades']/r3['days']:.1f}")

# Try confirm=1.5%, flat 5%, both directions, high max
print("\n=== Flat 5%, confirm=1.5%, max=30, exp=100% ===")
r4 = sim(data, 0.015, [(0.0, 1.0)], 0.05, 0.05, 30, 1.0, capital)
if r4:
    print(f"  trades={r4['trades']} WR={r4['win_rate']*100:.1f}% CAGR={r4['cagr']*100:.0f}% MDD={r4['mdd']*100:.1f}%")
    print(f"  daily_avg={r4['daily_avg']:,.0f} total={r4['total_pnl']:,.0f} days={r4['days']}")
    print(f"  trades/day={r4['trades']/r4['days']:.1f}")
