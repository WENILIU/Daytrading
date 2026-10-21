import pickle, pandas as pd, numpy as np

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'

sig = pd.read_pickle(f'{OUTPUT_DIR}/gap_fade_signals_2010.pkl')
sig['date'] = pd.to_datetime(sig['date'])

CAPITAL = 4_500_000
SL_PCT = 0.06
TP_PCT = 0.04
MIN_PRICE = 30
MAX_PRICE = 225
COST = 0.0017

# Pre-compute PnL for all signals (direction-agnostic)
def calc_pnl(df, direction):
    if direction == 'SHORT':
        sl_hit = df['day_high'] >= df['entry'] * (1 + SL_PCT)
        tp_hit = df['day_low'] <= df['entry'] * (1 - TP_PCT)
        return np.where(tp_hit, TP_PCT, np.where(sl_hit, -SL_PCT, (df['entry'] - df['day_close']) / df['entry'])) - COST
    else:
        sl_hit = df['day_low'] <= df['entry'] * (1 - SL_PCT)
        tp_hit = df['day_high'] >= df['entry'] * (1 + TP_PCT)
        return np.where(tp_hit, TP_PCT, np.where(sl_hit, -SL_PCT, (df['day_close'] - df['entry']) / df['entry'])) - COST

# Prepare signals
short = sig[sig['direction'] == 'SHORT'].copy()
short = short[short['adj_gap'] >= 0.05]
short = short[(short['entry'] >= MIN_PRICE) & (short['entry'] <= MAX_PRICE)]
short['pnl'] = calc_pnl(short, 'SHORT')

long = sig[sig['direction'] == 'LONG'].copy()
long = long[long['adj_gap'] <= -0.05]
long = long[(long['entry'] >= MIN_PRICE) & (long['entry'] <= MAX_PRICE)]
long['pnl'] = calc_pnl(long, 'LONG')

all_sig = pd.concat([short, long], ignore_index=True)
all_sig['_abs_gap'] = all_sig['adj_gap'].abs()
print(f'Base signals: {len(all_sig)}')

# === PARAMETER SWEEP ===
print('\n' + '=' * 70)
print('PARAMETER SWEEP: Finding CAGR ~100% / MDD < -20%')
print('=' * 70)

results = []

for gap_thresh in [0.03, 0.04, 0.05]:
    for base_pos in [0.05, 0.08, 0.10, 0.12, 0.15, 0.20]:
        for high_mult in [1.0, 1.5, 2.0]:
            for max_pos in [10, 15, 20]:
                for max_exp in [0.50, 0.70, 0.85]:
                    # Filter by gap threshold
                    subset = all_sig[all_sig['_abs_gap'] >= gap_thresh].copy()
                    
                    # Position sizing
                    subset['pos_pct'] = np.where(subset['_abs_gap'] > 0.07, base_pos * high_mult, base_pos)
                    
                    # 整張
                    subset['shares'] = np.floor(subset['pos_pct'] * CAPITAL / subset['entry'] / 1000).astype(int) * 1000
                    subset = subset[subset['shares'] >= 1000]
                    subset['actual_pos'] = (subset['shares'] * subset['entry']) / CAPITAL
                    
                    # Daily limits
                    subset = subset.sort_values(['date', '_abs_gap'], ascending=[True, False])
                    subset['day_rank'] = subset.groupby('date').cumcount()
                    subset = subset[subset['day_rank'] < max_pos]
                    subset['cum_exp'] = subset.groupby('date')['actual_pos'].cumsum()
                    subset = subset[subset['cum_exp'] <= max_exp]
                    
                    if len(subset) < 100:
                        continue
                    
                    subset['dollar_pnl'] = subset['pnl'] * subset['actual_pos'] * CAPITAL
                    daily_pnl = subset.groupby('date')['dollar_pnl'].sum()
                    daily_ret = daily_pnl / CAPITAL
                    
                    cum = (1 + daily_ret).cumprod()
                    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
                    cagr = cum.iloc[-1] ** (1/years) - 1
                    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
                    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
                    
                    results.append({
                        'gap': gap_thresh, 'base_pos': base_pos, 'high_mult': high_mult,
                        'max_pos': max_pos, 'max_exp': max_exp,
                        'trades': len(subset), 'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe,
                        'wr': (subset['pnl'] > 0).mean()
                    })

res_df = pd.DataFrame(results)
print(f'Tested: {len(res_df)} combinations')

# Filter: CAGR > 80% and MDD > -20%
target = res_df[(res_df['cagr'] > 0.80) & (res_df['mdd'] > -0.20)]
print(f'Matching target (CAGR>80%, MDD>-20%): {len(target)}')

# Sort by Sharpe (best risk-adjusted)
print('\n--- TOP 20 by Sharpe (CAGR>80%, MDD>-20%) ---')
best = target.sort_values('sharpe', ascending=False).head(20)
for _, r in best.iterrows():
    print(f'  Gap>{r["gap"]*100:.0f}% Pos={r["base_pos"]*100:.0f}%x{r["high_mult"]:.1f} MaxPos={int(r["max_pos"])} Exp={r["max_exp"]*100:.0f}% | '
          f'{int(r["trades"])} trades | CAGR={r["cagr"]*100:.0f}% MDD={r["mdd"]*100:.1f}% Sharpe={r["sharpe"]:.1f}')

# Sort by CAGR (highest return within MDD limit)
print('\n--- TOP 20 by CAGR (MDD>-20%) ---')
best2 = res_df[res_df['mdd'] > -0.20].sort_values('cagr', ascending=False).head(20)
for _, r in best2.iterrows():
    print(f'  Gap>{r["gap"]*100:.0f}% Pos={r["base_pos"]*100:.0f}%x{r["high_mult"]:.1f} MaxPos={int(r["max_pos"])} Exp={r["max_exp"]*100:.0f}% | '
          f'{int(r["trades"])} trades | CAGR={r["cagr"]*100:.0f}% MDD={r["mdd"]*100:.1f}% Sharpe={r["sharpe"]:.1f}')

# Best near 100% CAGR with lowest MDD
print('\n--- BEST: CAGR closest to 100% with lowest MDD ---')
near100 = res_df[(res_df['cagr'] > 0.90) & (res_df['cagr'] < 1.20)]
if len(near100) > 0:
    best3 = near100.sort_values('mdd', ascending=False).head(10)
    for _, r in best3.iterrows():
        print(f'  Gap>{r["gap"]*100:.0f}% Pos={r["base_pos"]*100:.0f}%x{r["high_mult"]:.1f} MaxPos={int(r["max_pos"])} Exp={r["max_exp"]*100:.0f}% | '
              f'{int(r["trades"])} trades | CAGR={r["cagr"]*100:.0f}% MDD={r["mdd"]*100:.1f}% Sharpe={r["sharpe"]:.1f}')
