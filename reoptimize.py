import pickle, os, json
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'

print('=' * 60)
print('FULL RE-OPTIMIZATION: Entry timing + SL/TP')
print('=' * 60)

# Load signals
old_signals = pd.read_pickle(f'{OUTPUT_DIR}/full_1min_results_v3.pkl')
old_signals['date'] = pd.to_datetime(old_signals['date'])
new_signals = pd.read_pickle(f'{OUTPUT_DIR}/full_1min_results_2026H2.pkl')
new_signals['date'] = pd.to_datetime(new_signals['date'])
all_signals = pd.concat([old_signals, new_signals], ignore_index=True)

# Get adj_gap
orig_sig = pd.read_pickle(f'{OUTPUT_DIR}/gap_fade_signals_2010.pkl')
orig_sig['date'] = pd.to_datetime(orig_sig['date'])
adj_lookup = orig_sig[['date', 'stock', 'adj_gap']].drop_duplicates(subset=['date', 'stock'])
all_signals = all_signals.merge(adj_lookup, on=['date', 'stock'], how='left', suffixes=('', '_o'))
if 'adj_gap_o' in all_signals.columns:
    if 'adj_gap' in all_signals.columns:
        all_signals['adj_gap'] = all_signals['adj_gap'].fillna(all_signals['adj_gap_o'])
    else:
        all_signals['adj_gap'] = all_signals['adj_gap_o']
    all_signals = all_signals.drop(columns=['adj_gap_o'])

all_signals = all_signals[all_signals['adj_gap'].abs() >= 0.05].copy()
print(f'Signals: {len(all_signals)}')

# Load 1-min index
idx = pickle.load(open(f'{OUTPUT_DIR}/stock_1min_index.pkl', 'rb'))

# Entry times to test (minutes after 9:00)
ENTRY_TIMES = [1, 2, 3, 5, 10, 15, 20, 30]
# SL/TP to test
SL_TPS = [(0.03, 0.03), (0.03, 0.05), (0.05, 0.05), (0.05, 0.03), (0.04, 0.04), 
          (0.02, 0.03), (0.03, 0.02), (0.02, 0.02), (0.05, 0.08), (0.08, 0.05)]

# Process all signals, store day candles for each
print('Loading 1-min data and computing PnL for all entry/SLTP combos...')

stock_groups = all_signals.groupby('stock')
all_results = []  # (entry_min, sl, tp, date, stock, pnl, entry_price, adj_gap)

processed = 0
for sid, group in stock_groups:
    # Load day data
    day_data = {}
    if sid in idx:
        path = idx[sid]
        if os.path.isdir(path):
            files = [f for f in os.listdir(path) if f.endswith('.json')]
            for f in files:
                fpath = os.path.join(path, f)
                try:
                    with open(fpath, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                    if isinstance(data, dict) and 'data' in data:
                        for c in data['data']:
                            d = c['date'][:10]
                            if d not in day_data:
                                day_data[d] = []
                            day_data[d].append(c)
                except:
                    pass
                del data
    
    for d in day_data:
        day_data[d] = sorted(day_data[d], key=lambda x: x['date'])
    
    if not day_data:
        continue
    
    for _, sig in group.iterrows():
        date = sig['date']
        date_str = date.strftime('%Y-%m-%d')
        
        if date_str not in day_data:
            continue
        
        day_candles = day_data[date_str]
        if len(day_candles) < 31:
            continue
        
        open_price = day_candles[0]['open']
        
        # Price filter on open
        if open_price < 30 or open_price > 225:
            continue
        
        for entry_min in ENTRY_TIMES:
            if entry_min >= len(day_candles):
                continue
            
            # Entry price = close of candle at entry_min
            entry_price = day_candles[entry_min - 1]['close']
            
            if entry_price < 30 or entry_price > 225:
                continue
            
            # Calculate early move (for reference)
            first_n = day_candles[:entry_min]
            min_in_window = min(c['low'] for c in first_n)
            early_move = (open_price - min_in_window) / open_price
            
            after = day_candles[entry_min:]
            
            for sl_pct, tp_pct in SL_TPS:
                sl_price = entry_price * (1 + sl_pct)
                tp_price = entry_price * (1 - tp_pct)
                
                pnl = None
                exit_reason = None
                
                for c in after:
                    if c['high'] >= sl_price:
                        pnl = -sl_pct
                        exit_reason = 'SL'
                        break
                    if c['low'] <= tp_price:
                        pnl = tp_pct
                        exit_reason = 'TP'
                        break
                
                if pnl is None:
                    last_close = day_candles[-1]['close']
                    pnl = (entry_price - last_close) / entry_price
                    exit_reason = 'FORCE'
                
                pnl -= 0.0017  # cost
                
                all_results.append({
                    'entry_min': entry_min,
                    'sl': sl_pct,
                    'tp': tp_pct,
                    'date': date,
                    'stock': sid,
                    'pnl': pnl,
                    'entry_price': entry_price,
                    'open_price': open_price,
                    'early_move': early_move,
                    'adj_gap': sig['adj_gap'],
                    'exit_reason': exit_reason
                })
    
    processed += 1
    if processed % 200 == 0:
        print(f'  Stocks processed: {processed}/{len(stock_groups)}, results: {len(all_results)}')
    
    del day_data

print(f'\nTotal results: {len(all_results)}')
df = pd.DataFrame(all_results)
pickle.dump(df, open(f'{OUTPUT_DIR}/all_entry_sltp_results.pkl', 'wb'))
print('Saved all_entry_sltp_results.pkl')

# === ANALYSIS ===
print(f'\n{"=" * 60}')
print('OPTIMAL ENTRY TIME + SL/TP')
print(f'{"=" * 60}')

# Group by entry_min, sl, tp
summary = df.groupby(['entry_min', 'sl', 'tp']).agg(
    trades=('pnl', 'count'),
    win_rate=('pnl', lambda x: (x > 0).mean()),
    avg_pnl=('pnl', 'mean'),
    total_pnl=('pnl', 'sum'),
    std_pnl=('pnl', 'std'),
    mdd_proxy=('pnl', lambda x: x.min())
).reset_index()

summary['sharpe_proxy'] = summary['avg_pnl'] / summary['std_pnl'] * np.sqrt(252)

# Sort by avg_pnl (most profitable per trade)
print('\n--- TOP 20 by Avg PnL (min 100 trades) ---')
top = summary[summary['trades'] >= 100].sort_values('avg_pnl', ascending=False).head(20)
for _, r in top.iterrows():
    print(f'  Entry={r["entry_min"]:2d}min SL={r["sl"]*100:.0f}% TP={r["tp"]*100:.0f}% | '
          f'{r["trades"]:4d} trades | WR={r["win_rate"]*100:.1f}% | '
          f'AvgPnL={r["avg_pnl"]*100:.2f}% | Sharpe={r["sharpe_proxy"]:.1f}')

# Sort by Sharpe
print('\n--- TOP 20 by Sharpe (min 100 trades) ---')
top2 = summary[summary['trades'] >= 100].sort_values('sharpe_proxy', ascending=False).head(20)
for _, r in top2.iterrows():
    print(f'  Entry={r["entry_min"]:2d}min SL={r["sl"]*100:.0f}% TP={r["tp"]*100:.0f}% | '
          f'{r["trades"]:4d} trades | WR={r["win_rate"]*100:.1f}% | '
          f'AvgPnL={r["avg_pnl"]*100:.2f}% | Sharpe={r["sharpe_proxy"]:.1f}')

# Sort by total PnL
print('\n--- TOP 20 by Total PnL (min 100 trades) ---')
top3 = summary[summary['trades'] >= 100].sort_values('total_pnl', ascending=False).head(20)
for _, r in top3.iterrows():
    print(f'  Entry={r["entry_min"]:2d}min SL={r["sl"]*100:.0f}% TP={r["tp"]*100:.0f}% | '
          f'{r["trades"]:4d} trades | WR={r["win_rate"]*100:.1f}% | '
          f'AvgPnL={r["avg_pnl"]*100:.2f}% | Total={r["total_pnl"]:.0f}')

print('\n' + '=' * 60)
print('DONE')
print('=' * 60)
