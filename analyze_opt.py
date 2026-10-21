import pickle, pandas as pd, numpy as np

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'
df = pd.read_pickle(f'{OUTPUT_DIR}/all_entry_sltp_results.pkl')
print(f'Loaded: {len(df)} results')

# Group by entry_min, sl, tp
summary = df.groupby(['entry_min', 'sl', 'tp']).agg(
    trades=('pnl', 'count'),
    win_rate=('pnl', lambda x: (x > 0).mean()),
    avg_pnl=('pnl', 'mean'),
    total_pnl=('pnl', 'sum'),
    std_pnl=('pnl', 'std'),
    worst=('pnl', 'min')
).reset_index()

summary['sharpe_proxy'] = summary['avg_pnl'] / summary['std_pnl'] * np.sqrt(252)

# TOP by Avg PnL
print('\n' + '=' * 70)
print('TOP 20 by Avg PnL (min 100 trades)')
print('=' * 70)
top = summary[summary['trades'] >= 100].sort_values('avg_pnl', ascending=False).head(20)
for _, r in top.iterrows():
    em = int(r['entry_min'])
    sl = int(r['sl'] * 100)
    tp = int(r['tp'] * 100)
    print(f'  Entry={em:2d}min SL={sl}% TP={tp}% | {int(r["trades"]):4d} trades | '
          f'WR={r["win_rate"]*100:.1f}% | AvgPnL={r["avg_pnl"]*100:.2f}% | Sharpe={r["sharpe_proxy"]:.1f}')

# TOP by Sharpe
print('\n' + '=' * 70)
print('TOP 20 by Sharpe (min 100 trades)')
print('=' * 70)
top2 = summary[summary['trades'] >= 100].sort_values('sharpe_proxy', ascending=False).head(20)
for _, r in top2.iterrows():
    em = int(r['entry_min'])
    sl = int(r['sl'] * 100)
    tp = int(r['tp'] * 100)
    print(f'  Entry={em:2d}min SL={sl}% TP={tp}% | {int(r["trades"]):4d} trades | '
          f'WR={r["win_rate"]*100:.1f}% | AvgPnL={r["avg_pnl"]*100:.2f}% | Sharpe={r["sharpe_proxy"]:.1f}')

# TOP by Total PnL
print('\n' + '=' * 70)
print('TOP 20 by Total PnL (min 100 trades)')
print('=' * 70)
top3 = summary[summary['trades'] >= 100].sort_values('total_pnl', ascending=False).head(20)
for _, r in top3.iterrows():
    em = int(r['entry_min'])
    sl = int(r['sl'] * 100)
    tp = int(r['tp'] * 100)
    print(f'  Entry={em:2d}min SL={sl}% TP={tp}% | {int(r["trades"]):4d} trades | '
          f'WR={r["win_rate"]*100:.1f}% | AvgPnL={r["avg_pnl"]*100:.2f}% | Total={r["total_pnl"]:.0f}')

# Entry time comparison (best SL/TP for each entry time)
print('\n' + '=' * 70)
print('BEST SL/TP FOR EACH ENTRY TIME')
print('=' * 70)
for em in sorted(df['entry_min'].unique()):
    sub = summary[summary['entry_min'] == em].sort_values('avg_pnl', ascending=False).head(1)
    if len(sub) > 0:
        r = sub.iloc[0]
        sl = int(r['sl'] * 100)
        tp = int(r['tp'] * 100)
        print(f'  Entry={int(em):2d}min: best SL={sl}% TP={tp}% | {int(r["trades"]):4d} trades | '
              f'WR={r["win_rate"]*100:.1f}% | AvgPnL={r["avg_pnl"]*100:.2f}% | Sharpe={r["sharpe_proxy"]:.1f}')
