import pickle, pandas as pd, numpy as np
from itertools import product
import warnings
warnings.filterwarnings('ignore')

# Load 1-min confirmed results (most realistic)
data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])

# Also load daily signals for longer period validation
daily_signals = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl', 'rb'))
print(f"1-min data: {len(data)} trades, {data['date'].min().date()} to {data['date'].max().date()}")
print(f"Daily signals: {len(daily_signals)} signals")
if isinstance(daily_signals, pd.DataFrame):
    print(f"  Columns: {list(daily_signals.columns)[:10]}")

# === OPTIMIZATION on 1-min data ===
# Parameters to sweep:
# 1. confirm_drop_min: minimum 15-min move to enter (filter out noise)
# 2. tier_thresholds: where to cut tiers
# 3. tier_multipliers: position size per tier
# 4. base_position: base % per trade
# 5. max_positions: daily cap
# 6. max_exposure: total daily exposure cap

def calc_direction_move(row):
    """Calculate favorable move for our direction"""
    if row['direction'] == 'SHORT':
        return -row['early_move_15']  # positive = price dropped = good for short
    else:
        return row['early_move_15']   # positive = price rose = good for long

data['fav_move'] = data.apply(calc_direction_move, axis=1)

def simulate(params, trade_data):
    """Simulate with given parameters"""
    confirm_min = params['confirm_min']
    tiers = params['tiers']  # list of (min_move, multiplier)
    base_short = params['base_short']
    base_long = params['base_long']
    max_pos = params['max_pos']
    max_exp = params['max_exp']
    capital = 4_500_000
    
    # Filter: only confirmed trades
    confirmed = trade_data[trade_data['fav_move'] >= confirm_min].copy()
    if len(confirmed) == 0:
        return None
    
    # Assign tier multiplier
    def get_multiplier(fav_move):
        mult = 0
        for min_move, m in tiers:
            if fav_move >= min_move:
                mult = m
                break
        return mult
    
    confirmed['multiplier'] = confirmed['fav_move'].apply(get_multiplier)
    confirmed = confirmed[confirmed['multiplier'] > 0]
    
    if len(confirmed) == 0:
        return None
    
    # Calculate position size
    confirmed['pos_pct'] = confirmed.apply(
        lambda r: (base_short if r['direction']=='SHORT' else base_long) * r['multiplier'], axis=1)
    
    # Apply daily limits (sort by fav_move descending = best signals first)
    confirmed = confirmed.sort_values(['date', 'fav_move'], ascending=[True, False])
    
    results = []
    for date, day_trades in confirmed.groupby('date'):
        day_trades = day_trades.head(max_pos)
        total_exp = 0
        for _, trade in day_trades.iterrows():
            if total_exp + trade['pos_pct'] > max_exp:
                continue
            total_exp += trade['pos_pct']
            dollar_pnl = trade['pnl'] * trade['pos_pct'] * capital
            results.append({'date': date, 'pnl': dollar_pnl, 'pos_pct': trade['pos_pct']})
    
    if not results:
        return None
    
    res_df = pd.DataFrame(results)
    daily_pnl = res_df.groupby('date')['pnl'].sum()
    daily_ret = daily_pnl / capital
    
    # Metrics
    cum = (1 + daily_ret).cumprod()
    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
    if years < 0.5:
        return None
    cagr = cum.iloc[-1] ** (1/years) - 1
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0
    
    return {
        'cagr': cagr,
        'mdd': mdd,
        'sharpe': sharpe,
        'trades': len(res_df),
        'win_rate': (res_df['pnl'] > 0).mean(),
        'avg_daily_trades': len(res_df) / len(daily_pnl),
        'calmar': cagr / abs(mdd) if mdd != 0 else 0,
    }

# === Parameter Grid ===
print("\n" + "="*60)
print("PARAMETER OPTIMIZATION")
print("="*60)

results = []

# Sweep parameters
confirm_mins = [0.0, 0.005, 0.01, 0.015, 0.02]
tier_options = [
    [(0.03, 2.0), (0.015, 1.5), (0.005, 1.0), (0.0, 0.5)],  # current
    [(0.03, 2.0), (0.015, 1.5), (0.005, 1.0)],                # no T2
    [(0.03, 2.5), (0.015, 1.5), (0.005, 1.0)],                # aggressive T5
    [(0.02, 2.0), (0.01, 1.5), (0.005, 1.0)],                 # lower thresholds
    [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)],                # very aggressive
    [(0.015, 2.0), (0.005, 1.0)],                              # simple 2-tier
    [(0.03, 2.0), (0.015, 1.5), (0.01, 1.2), (0.005, 1.0)],  # 4-tier fine
]
base_shorts = [0.03, 0.04, 0.05, 0.06, 0.07]
base_longs = [0.015, 0.02, 0.025, 0.03]
max_positions = [10, 15, 20, 30]
max_exposures = [0.5, 0.6, 0.7, 0.8]

count = 0
for cm, tiers, bs, bl, mp, me in product(
    confirm_mins, tier_options, base_shorts, base_longs, max_positions, max_exposures):
    
    params = {
        'confirm_min': cm,
        'tiers': tiers,
        'base_short': bs,
        'base_long': bl,
        'max_pos': mp,
        'max_exp': me,
    }
    
    r = simulate(params, data)
    if r and r['cagr'] > 0 and r['mdd'] > -0.15:
        r['params'] = params
        results.append(r)
    count += 1

print(f"Tested {count} combinations, {len(results)} valid results")

# Sort by Calmar ratio (CAGR / |MDD|) - best risk-adjusted
results_df = pd.DataFrame([{k: v for k, v in r.items() if k != 'params'} | 
                          {'confirm_min': r['params']['confirm_min'],
                           'tier_idx': tier_options.index(r['params']['tiers']),
                           'base_short': r['params']['base_short'],
                           'base_long': r['params']['base_long'],
                           'max_pos': r['params']['max_pos'],
                           'max_exp': r['params']['max_exp']}
                          for r in results])

# Top by Calmar
print("\n=== TOP 10 by Calmar Ratio ===")
top = results_df.nlargest(10, 'calmar')
for _, row in top.iterrows():
    print(f"  Calmar={row['calmar']:.1f} CAGR={row['cagr']*100:.0f}% MDD={row['mdd']*100:.1f}% "
          f"Sharpe={row['sharpe']:.1f} WR={row['win_rate']*100:.0f}% "
          f"confirm={row['confirm_min']*100:.1f}% tiers=#{row['tier_idx']} "
          f"bs={row['base_short']*100:.0f}% bl={row['base_long']*100:.1f}% "
          f"maxpos={row['max_pos']} maxexp={row['max_exp']*100:.0f}%")

# Top by CAGR with MDD < -5%
print("\n=== TOP 10 by CAGR (MDD > -5%) ===")
safe = results_df[results_df['mdd'] > -0.05]
top2 = safe.nlargest(10, 'cagr')
for _, row in top2.iterrows():
    print(f"  CAGR={row['cagr']*100:.0f}% MDD={row['mdd']*100:.1f}% Calmar={row['calmar']:.1f} "
          f"Sharpe={row['sharpe']:.1f} WR={row['win_rate']*100:.0f}% "
          f"trades/day={row['avg_daily_trades']:.1f} "
          f"confirm={row['confirm_min']*100:.1f}% tiers=#{row['tier_idx']} "
          f"bs={row['base_short']*100:.0f}% bl={row['base_long']*100:.1f}% "
          f"maxpos={row['max_pos']} maxexp={row['max_exp']*100:.0f}%")

# Top by Sharpe
print("\n=== TOP 10 by Sharpe Ratio ===")
top3 = results_df.nlargest(10, 'sharpe')
for _, row in top3.iterrows():
    print(f"  Sharpe={row['sharpe']:.1f} CAGR={row['cagr']*100:.0f}% MDD={row['mdd']*100:.1f}% "
          f"Calmar={row['calmar']:.1f} WR={row['win_rate']*100:.0f}% "
          f"confirm={row['confirm_min']*100:.1f}% tiers=#{row['tier_idx']} "
          f"bs={row['base_short']*100:.0f}% bl={row['base_long']*100:.1f}% "
          f"maxpos={row['max_pos']} maxexp={row['max_exp']*100:.0f}%")

# Save best params
best = results_df.nlargest(1, 'calmar').iloc[0]
print(f"\n\n=== BEST (by Calmar) ===")
print(f"  confirm_min: {best['confirm_min']}")
print(f"  tier_idx: {best['tier_idx']}")
print(f"  base_short: {best['base_short']}")
print(f"  base_long: {best['base_long']}")
print(f"  max_pos: {best['max_pos']}")
print(f"  max_exp: {best['max_exp']}")
print(f"  CAGR: {best['cagr']*100:.1f}%")
print(f"  MDD: {best['mdd']*100:.1f}%")
print(f"  Sharpe: {best['sharpe']:.2f}")
print(f"  Win Rate: {best['win_rate']*100:.1f}%")
print(f"  Avg trades/day: {best['avg_daily_trades']:.1f}")

pickle.dump(results_df, open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\opt_results.pkl', 'wb'))
