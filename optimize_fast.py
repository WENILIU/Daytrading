import pickle, pandas as pd, numpy as np
from itertools import product
import warnings
warnings.filterwarnings('ignore')

data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])

# Pre-compute favorable move
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

print(f"Data: {len(data)} trades, {data['date'].min().date()} to {data['date'].max().date()}")

def fast_simulate(confirm_min, tiers, base_short, base_long, max_pos, max_exp, capital=4_500_000):
    """Vectorized simulation"""
    # Filter by confirmation
    mask = data['fav_move'] >= confirm_min
    subset = data[mask].copy()
    if len(subset) == 0:
        return None
    
    # Assign tier multiplier (vectorized)
    mult = np.zeros(len(subset))
    for min_move, m in sorted(tiers, reverse=True):
        cond = (subset['fav_move'].values >= min_move) & (mult == 0)
        mult[cond] = m
    subset['multiplier'] = mult
    subset = subset[subset['multiplier'] > 0]
    if len(subset) == 0:
        return None
    
    # Position size
    subset['pos_pct'] = np.where(
        subset['direction'] == 'SHORT', base_short, base_long) * subset['multiplier']
    
    # Sort by date + fav_move (best first within each day)
    subset = subset.sort_values(['date', 'fav_move'], ascending=[True, False])
    
    # Apply daily limits: rank within day, keep top max_pos
    subset['day_rank'] = subset.groupby('date').cumcount()
    subset = subset[subset['day_rank'] < max_pos]
    
    # Apply exposure limit: cumulative pos_pct within day
    subset['cum_exp'] = subset.groupby('date')['pos_pct'].cumsum()
    subset = subset[subset['cum_exp'] <= max_exp]
    
    if len(subset) == 0:
        return None
    
    # Calculate PnL
    subset['dollar_pnl'] = subset['pnl'] * subset['pos_pct'] * capital
    
    # Daily aggregation
    daily_pnl = subset.groupby('date')['dollar_pnl'].sum()
    daily_ret = daily_pnl / capital
    
    # Metrics
    cum = (1 + daily_ret).cumprod()
    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
    if years < 0.5 or cum.iloc[-1] <= 0:
        return None
    cagr = cum.iloc[-1] ** (1/years) - 1
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0
    
    return {
        'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe,
        'trades': len(subset), 'win_rate': (subset['pnl'] > 0).mean(),
        'avg_daily_trades': len(subset) / len(daily_pnl),
        'calmar': cagr / abs(mdd) if mdd != 0 else 0,
        'total_days': len(daily_pnl),
    }

# === Parameter Grid (reduced for speed) ===
print("\nOptimizing...")

results = []

confirm_mins = [0.0, 0.003, 0.005, 0.01, 0.015, 0.02]
tier_options = [
    [(0.03, 2.0), (0.015, 1.5), (0.005, 1.0), (0.0, 0.5)],   # 0: current 4-tier
    [(0.03, 2.0), (0.015, 1.5), (0.005, 1.0)],                  # 1: no T2
    [(0.03, 2.5), (0.015, 1.5), (0.005, 1.0)],                  # 2: aggressive T5
    [(0.02, 2.0), (0.01, 1.5), (0.005, 1.0)],                   # 3: lower thresholds
    [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)],                  # 4: very aggressive
    [(0.015, 2.0), (0.005, 1.0)],                                # 5: simple 2-tier
    [(0.03, 2.0), (0.015, 1.5), (0.01, 1.2), (0.005, 1.0)],    # 6: fine 4-tier
    [(0.03, 2.0), (0.015, 1.5), (0.005, 1.0), (0.003, 0.7)],   # 7: add micro tier
]
base_shorts = [0.03, 0.04, 0.05, 0.06, 0.07, 0.08]
base_longs = [0.015, 0.02, 0.025, 0.03, 0.035]
max_positions = [10, 15, 20, 30, 50]
max_exposures = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

total = len(confirm_mins) * len(tier_options) * len(base_shorts) * len(base_longs) * len(max_positions) * len(max_exposures)
print(f"Grid size: {total}")

count = 0
for cm, ti, bs, bl, mp, me in product(
    range(len(confirm_mins)), range(len(tier_options)), 
    range(len(base_shorts)), range(len(base_longs)),
    range(len(max_positions)), range(len(max_exposures))):
    
    r = fast_simulate(
        confirm_mins[cm], tier_options[ti], 
        base_shorts[bs], base_longs[bl],
        max_positions[mp], max_exposures[me])
    
    if r and r['cagr'] > 0.1 and r['mdd'] > -0.15 and r['trades'] > 100:
        r.update({
            'confirm_min': confirm_mins[cm], 'tier_idx': ti,
            'base_short': base_shorts[bs], 'base_long': base_longs[bl],
            'max_pos': max_positions[mp], 'max_exp': max_exposures[me],
        })
        results.append(r)
    count += 1
    if count % 5000 == 0:
        print(f"  Progress: {count}/{total} ({len(results)} valid)")

print(f"\nDone. {len(results)} valid results from {count} tested.")

results_df = pd.DataFrame(results)

# Top by Calmar
print("\n=== TOP 15 by Calmar (CAGR/|MDD|) ===")
for _, row in results_df.nlargest(15, 'calmar').iterrows():
    print(f"  Cal={row['calmar']:.0f} CAGR={row['cagr']*100:.0f}% MDD={row['mdd']*100:.1f}% "
          f"Sh={row['sharpe']:.1f} WR={row['win_rate']*100:.0f}% "
          f"cm={row['confirm_min']*100:.1f}% t={row['tier_idx']} "
          f"bs={row['base_short']*100:.0f}% bl={row['base_long']*100:.1f}% "
          f"mp={row['max_pos']} me={row['max_exp']*100:.0f}% "
          f"trades/d={row['avg_daily_trades']:.1f}")

# Top by CAGR with MDD > -5%
print("\n=== TOP 15 by CAGR (MDD > -5%) ===")
safe = results_df[results_df['mdd'] > -0.05]
for _, row in safe.nlargest(15, 'cagr').iterrows():
    print(f"  CAGR={row['cagr']*100:.0f}% MDD={row['mdd']*100:.1f}% Cal={row['calmar']:.0f} "
          f"Sh={row['sharpe']:.1f} WR={row['win_rate']*100:.0f}% "
          f"cm={row['confirm_min']*100:.1f}% t={row['tier_idx']} "
          f"bs={row['base_short']*100:.0f}% bl={row['base_long']*100:.1f}% "
          f"mp={row['max_pos']} me={row['max_exp']*100:.0f}% "
          f"trades/d={row['avg_daily_trades']:.1f}")

# Top by Sharpe
print("\n=== TOP 15 by Sharpe ===")
for _, row in results_df.nlargest(15, 'sharpe').iterrows():
    print(f"  Sharpe={row['sharpe']:.1f} CAGR={row['cagr']*100:.0f}% MDD={row['mdd']*100:.1f}% "
          f"Cal={row['calmar']:.0f} WR={row['win_rate']*100:.0f}% "
          f"cm={row['confirm_min']*100:.1f}% t={row['tier_idx']} "
          f"bs={row['base_short']*100:.0f}% bl={row['base_long']*100:.1f}% "
          f"mp={row['max_pos']} me={row['max_exp']*100:.0f}% "
          f"trades/d={row['avg_daily_trades']:.1f}")

# Save
results_df.to_pickle(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\opt_results.pkl')
print("\nSaved to opt_results.pkl")
