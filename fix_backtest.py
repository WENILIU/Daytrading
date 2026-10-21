import pickle, os, json
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'

print('=' * 60)
print('FIXED BACKTEST: Entry at 9:15 price')
print('=' * 60)

# Load signals
old_signals = pd.read_pickle(f'{OUTPUT_DIR}/full_1min_results_v3.pkl')
old_signals['date'] = pd.to_datetime(old_signals['date'])

new_signals = pd.read_pickle(f'{OUTPUT_DIR}/full_1min_results_2026H2.pkl')
new_signals['date'] = pd.to_datetime(new_signals['date'])

all_signals = pd.concat([old_signals, new_signals], ignore_index=True)
all_signals = all_signals.sort_values('date').reset_index(drop=True)
print(f'Total signals to process: {len(all_signals)}')

# Get adj_gap from original signals
orig_sig = pd.read_pickle(f'{OUTPUT_DIR}/gap_fade_signals_2010.pkl')
orig_sig['date'] = pd.to_datetime(orig_sig['date'])
adj_lookup = orig_sig[['date', 'stock', 'adj_gap']].drop_duplicates(subset=['date', 'stock'])

# Merge adj_gap
all_signals = all_signals.merge(adj_lookup, on=['date', 'stock'], how='left', suffixes=('', '_o'))
if 'adj_gap_o' in all_signals.columns:
    if 'adj_gap' in all_signals.columns:
        all_signals['adj_gap'] = all_signals['adj_gap'].fillna(all_signals['adj_gap_o'])
    else:
        all_signals['adj_gap'] = all_signals['adj_gap_o']
    all_signals = all_signals.drop(columns=['adj_gap_o'])

# Filter: only signals with adj_gap >= 5%
all_signals = all_signals[all_signals['adj_gap'].abs() >= 0.05].copy()
print(f'After adj_gap >= 5% filter: {len(all_signals)}')

# Load 1-min index
idx = pickle.load(open(f'{OUTPUT_DIR}/stock_1min_index.pkl', 'rb'))

# Group by stock for memory efficiency
stock_groups = all_signals.groupby('stock')
print(f'Unique stocks: {len(stock_groups)}')

results = []
no_data = 0

for sid, group in stock_groups:
    # Load this stock's 1-min data once
    day_data = {}  # date_str -> candles
    
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
                # Free memory
                del data
    
    # Sort each day's candles chronologically (API returns newest first)
    for d in day_data:
        day_data[d] = sorted(day_data[d], key=lambda x: x['date'])
    
    if not day_data:
        no_data += 1
        continue
    
    # Process each signal for this stock
    for _, sig in group.iterrows():
        date = sig['date']
        date_str = date.strftime('%Y-%m-%d')
        
        if date_str not in day_data:
            continue
        
        day_candles = day_data[date_str]
        if len(day_candles) < 16:
            continue
        
        # Confirmation: first 15 min must drop >= 2.5%
        first_15 = day_candles[:15]
        open_price = first_15[0]['open']
        min_price_15 = min(c['low'] for c in first_15)
        early_move = (open_price - min_price_15) / open_price
        
        if early_move < 0.025:
            continue
        
        # Entry = price at 9:15 (close of 15th candle)
        entry_price = day_candles[14]['close']
        
        # Price filter
        if entry_price < 30 or entry_price > 225:
            continue
        
        # SL/TP from entry, check AFTER 9:15 only
        sl_price = entry_price * 1.05
        tp_price = entry_price * 0.95
        
        pnl = None
        exit_reason = None
        
        for c in day_candles[15:]:
            if c['high'] >= sl_price:
                pnl = -0.05
                exit_reason = 'SL'
                break
            if c['low'] <= tp_price:
                pnl = 0.05
                exit_reason = 'TP'
                break
        
        if pnl is None:
            last_close = day_candles[-1]['close']
            pnl = (entry_price - last_close) / entry_price
            exit_reason = 'FORCE'
        
        pnl -= 0.0017
        
        results.append({
            'date': date,
            'stock': sid,
            'direction': 'SHORT',
            'pnl': pnl,
            'entry': entry_price,
            'open_price': open_price,
            'early_move_15': -early_move,
            'adj_gap': sig['adj_gap'],
            'exit_reason': exit_reason
        })
    
    # Clear memory for this stock
    del day_data
    
    if len(results) % 1000 == 0 and len(results) > 0:
        print(f'  Processed {len(results)} trades so far...')

results_df = pd.DataFrame(results)
print(f'\n  Stocks without data: {no_data}')
print(f'  Total confirmed trades: {len(results_df)}')

if len(results_df) > 0:
    wr = (results_df['pnl'] > 0).mean() * 100
    avg_pnl = results_df['pnl'].mean() * 100
    print(f'  Win rate: {wr:.1f}%')
    print(f'  Avg PnL: {avg_pnl:.2f}%')
    
    pickle.dump(results_df, open(f'{OUTPUT_DIR}/full_1min_results_v3_fixed.pkl', 'wb'))
    print('  Saved full_1min_results_v3_fixed.pkl')

print('\n' + '=' * 60)
print('DONE')
print('=' * 60)
