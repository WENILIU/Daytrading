import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

train = data[data['date'] < '2025-01-01']
test = data[data['date'] >= '2025-01-01']

def fast_sim(trade_data, confirm_min, tiers, base_short, base_long, max_pos, max_exp, capital=4_500_000):
    mask = trade_data['fav_move'] >= confirm_min
    subset = trade_data[mask].copy()
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
            'win_rate': (subset['pnl'] > 0).mean(),
            'calmar': cagr / abs(mdd) if mdd != 0 else 0}

tier_options = [
    [(0.03, 2.0), (0.015, 1.5), (0.005, 1.0), (0.0, 0.5)],
    [(0.03, 2.0), (0.015, 1.5), (0.005, 1.0)],
    [(0.03, 2.5), (0.015, 1.5), (0.005, 1.0)],
    [(0.02, 2.0), (0.01, 1.5), (0.005, 1.0)],
    [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)],
    [(0.015, 2.0), (0.005, 1.0)],
    [(0.03, 2.0), (0.015, 1.5), (0.01, 1.2), (0.005, 1.0)],
    [(0.03, 2.0), (0.015, 1.5), (0.005, 1.0), (0.003, 0.7)],
]

# Load full optimization results
opt = pd.read_pickle(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\opt_results.pkl')

# Walk-forward: test top params on 2025-2026
top5 = opt.nlargest(5, 'calmar')
print("=== Walk-Forward Validation ===")
print("Testing top-5 optimized params on OUT-OF-SAMPLE (2025-2026)")
print()

for _, r in top5.iterrows():
    cm = float(r['confirm_min'])
    ti = int(r['tier_idx'])
    bs = float(r['base_short'])
    bl = float(r['base_long'])
    mp = int(r['max_pos'])
    me = float(r['max_exp'])
    
    train_r = fast_sim(train, cm, tier_options[ti], bs, bl, mp, me)
    test_r = fast_sim(test, cm, tier_options[ti], bs, bl, mp, me)
    
    print(f"  confirm={cm*100:.1f}% tier={ti} bs={bs*100:.0f}% bl={bl*100:.1f}% mp={mp} me={me*100:.0f}%")
    if train_r:
        print(f"    TRAIN(23-24): CAGR={train_r['cagr']*100:.0f}% MDD={train_r['mdd']*100:.1f}% WR={train_r['win_rate']*100:.0f}%")
    if test_r:
        print(f"    TEST (25-26): CAGR={test_r['cagr']*100:.0f}% MDD={test_r['mdd']*100:.1f}% WR={test_r['win_rate']*100:.0f}% Sharpe={test_r['sharpe']:.1f}")
    else:
        print("    TEST: NO RESULTS")
    print()

# Conservative configs
print("\n=== CONSERVATIVE configs ===")
configs = [
    (0.015, 4, 0.06, 0.015, 10, 0.5),
    (0.015, 4, 0.07, 0.015, 10, 0.5),
    (0.02, 4, 0.07, 0.015, 10, 0.5),
    (0.02, 4, 0.08, 0.015, 10, 0.5),
    (0.015, 3, 0.06, 0.015, 10, 0.5),
    (0.01, 4, 0.06, 0.015, 15, 0.6),
    (0.01, 4, 0.07, 0.02, 15, 0.6),
    (0.005, 4, 0.05, 0.015, 15, 0.6),
    (0.005, 4, 0.06, 0.02, 20, 0.7),
]
for cm, ti, bs, bl, mp, me in configs:
    train_r = fast_sim(train, cm, tier_options[ti], bs, bl, mp, me)
    test_r = fast_sim(test, cm, tier_options[ti], bs, bl, mp, me)
    if train_r and test_r:
        print(f"  cm={cm*100:.1f}% t={ti} bs={bs*100:.0f}% bl={bl*100:.1f}% mp={mp} me={me*100:.0f}%")
        print(f"    TRAIN: CAGR={train_r['cagr']*100:.0f}% MDD={train_r['mdd']*100:.1f}% WR={train_r['win_rate']*100:.0f}%")
        print(f"    TEST:  CAGR={test_r['cagr']*100:.0f}% MDD={test_r['mdd']*100:.1f}% WR={test_r['win_rate']*100:.0f}%")
        print()
