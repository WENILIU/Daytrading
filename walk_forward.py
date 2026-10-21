import pickle, pandas as pd, numpy as np
from itertools import product
import warnings
warnings.filterwarnings('ignore')

data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

train = data[data['date'] < '2025-01-01']
test = data[data['date'] >= '2025-01-01']
print(f"Train: {len(train)} trades ({train['date'].min().date()} to {train['date'].max().date()})")
print(f"Test:  {len(test)} trades ({test['date'].min().date()} to {test['date'].max().date()})")

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

cm_vals = [0.0, 0.003, 0.005, 0.01, 0.015, 0.02]
bs_vals = [0.03, 0.05, 0.06, 0.07, 0.08]
bl_vals = [0.015, 0.02, 0.025, 0.03]
mp_vals = [10, 15, 20, 30]
me_vals = [0.5, 0.6, 0.7, 0.8]

print("\n=== Optimizing on TRAIN (2023-2024) ===")
train_results = []
for ci, ti, bi, li, mi, ei in product(
    range(len(cm_vals)), range(len(tier_options)),
    range(len(bs_vals)), range(len(bl_vals)),
    range(len(mp_vals)), range(len(me_vals))):
    
    r = fast_sim(train, cm_vals[ci], tier_options[ti], bs_vals[bi], bl_vals[li], mp_vals[mi], me_vals[ei])
    if r and r['cagr'] > 0.1 and r['mdd'] > -0.15 and r['trades'] > 50:
        r.update({'ci': ci, 'ti': ti, 'bi': bi, 'li': li, 'mi': mi, 'ei': ei})
        train_results.append(r)

train_df = pd.DataFrame(train_results)
print(f"Valid: {len(train_df)}")

top5 = train_df.nlargest(5, 'calmar')
print("\nTop 5 TRAIN params:")
for _, r in top5.iterrows():
    print(f"  TRAIN: Cal={r['calmar']:.0f} CAGR={r['cagr']*100:.0f}% MDD={r['mdd']*100:.1f}% WR={r['win_rate']*100:.0f}%")
    print(f"         cm={cm_vals[r['ci']]*100:.1f}% t={r['ti']} bs={bs_vals[r['bi']]*100:.0f}% bl={bl_vals[r['li']]*100:.1f}% mp={mp_vals[r['mi']]} me={me_vals[r['ei']]*100:.0f}%")
    
    # Out-of-sample test
    test_r = fast_sim(test, cm_vals[r['ci']], tier_options[r['ti']], bs_vals[r['bi']], bl_vals[r['li']], mp_vals[r['mi']], me_vals[r['ei']])
    if test_r:
        print(f"  TEST:  Cal={test_r['calmar']:.0f} CAGR={test_r['cagr']*100:.0f}% MDD={test_r['mdd']*100:.1f}% WR={test_r['win_rate']*100:.0f}% Sharpe={test_r['sharpe']:.1f}")
    else:
        print(f"  TEST:  NO RESULTS")
    print()

# Conservative params test
print("\n=== CONSERVATIVE (confirm=1.5-2%) ===")
for ci in [4, 5]:  # 1.5%, 2%
    for ti in [4, 3]:  # aggressive tiers
        for bi in [3, 4]:  # 7%, 8%
            train_r = fast_sim(train, cm_vals[ci], tier_options[ti], bs_vals[bi], bl_vals[0], mp_vals[0], me_vals[0])
            test_r = fast_sim(test, cm_vals[ci], tier_options[ti], bs_vals[bi], bl_vals[0], mp_vals[0], me_vals[0])
            if train_r and test_r:
                print(f"  cm={cm_vals[ci]*100:.1f}% t={ti} bs={bs_vals[bi]*100:.0f}% me=50%")
                print(f"    TRAIN: CAGR={train_r['cagr']*100:.0f}% MDD={train_r['mdd']*100:.1f}% WR={train_r['win_rate']*100:.0f}%")
                print(f"    TEST:  CAGR={test_r['cagr']*100:.0f}% MDD={test_r['mdd']*100:.1f}% WR={test_r['win_rate']*100:.0f}%")
                print()
