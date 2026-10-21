import pickle, os, json
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'

# Load the raw results for entry=1min (best)
df = pd.read_pickle(f'{OUTPUT_DIR}/all_entry_sltp_results.pkl')
# Focus on entry=1min, SL=5%, TP=8% (best combo)
best = df[(df['entry_min'] == 1) & (df['sl'] == 0.05) & (df['tp'] == 0.08)].copy()
print(f'Base strategy (Entry=1min, SL=5%, TP=8%): {len(best)} trades')
print(f'  WR: {(best["pnl"]>0).mean()*100:.1f}% | AvgPnL: {best["pnl"].mean()*100:.2f}%')

# Now load 1-min data to compute features for filtering
idx = pickle.load(open(f'{OUTPUT_DIR}/stock_1min_index.pkl', 'rb'))

# Load signals to get the dates/stocks
signals = best[['date', 'stock', 'adj_gap', 'early_move', 'entry_price', 'open_price']].copy()

# Compute features from 1-min data
print('\nComputing features...')

features = []
stock_groups = signals.groupby('stock')
processed = 0

for sid, group in stock_groups:
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
    
    for _, sig in group.iterrows():
        date_str = sig['date'].strftime('%Y-%m-%d')
        if date_str not in day_data:
            continue
        
        day = day_data[date_str]
        if len(day) < 5:
            continue
        
        open_price = day[0]['open']
        
        # Feature 1: Price direction in first 1 min
        price_1min = day[0]['close']
        price_change_1min = (price_1min - open_price) / open_price
        
        # Feature 2: Price direction in first 5 min
        min_5 = min(c['low'] for c in day[:5])
        max_5 = max(c['high'] for c in day[:5])
        price_change_5min = (day[4]['close'] - open_price) / open_price
        drop_5min = (open_price - min_5) / open_price
        
        # Feature 3: Volume in first 5 min vs total
        vol_5 = sum(c['volume'] for c in day[:5])
        vol_total = sum(c['volume'] for c in day)
        vol_ratio_5 = vol_5 / vol_total if vol_total > 0 else 0
        
        # Feature 4: Sell volume ratio (approximate: candles where close < open)
        sell_vol = sum(c['volume'] for c in day[:5] if c['close'] < c['open'])
        total_vol_5 = sum(c['volume'] for c in day[:5])
        sell_ratio = sell_vol / total_vol_5 if total_vol_5 > 0 else 0.5
        
        # Feature 5: Gap size
        adj_gap = sig['adj_gap']
        
        features.append({
            'date': sig['date'],
            'stock': sid,
            'price_change_1min': price_change_1min,
            'price_change_5min': price_change_5min,
            'drop_5min': drop_5min,
            'vol_ratio_5': vol_ratio_5,
            'sell_ratio': sell_ratio,
            'adj_gap': adj_gap,
            'pnl': sig['pnl'] if 'pnl' in sig else 0
        })
    
    del day_data
    processed += 1
    if processed % 200 == 0:
        print(f'  {processed}/{len(stock_groups)}...')

feat_df = pd.DataFrame(features)
# Merge with PnL
feat_df = feat_df.merge(best[['date', 'stock', 'pnl']], on=['date', 'stock'], how='left', suffixes=('', '_best'))
if 'pnl_best' in feat_df.columns:
    feat_df['pnl'] = feat_df['pnl_best']
    feat_df = feat_df.drop(columns=['pnl_best'])

pickle.dump(feat_df, open(f'{OUTPUT_DIR}/features_entry1min.pkl', 'wb'))
print(f'\nFeatures computed: {len(feat_df)}')

# === FILTER ANALYSIS ===
print(f'\n{"=" * 70}')
print('FILTER ANALYSIS (Entry=1min, SL=5%, TP=8%)')
print(f'{"=" * 70}')

# 1. Price direction in first 1 min
print('\n--- Price change at 9:01 (1 min after open) ---')
for label, cond in [
    ('Dropped >2%', feat_df['price_change_1min'] < -0.02),
    ('Dropped 1-2%', (feat_df['price_change_1min'] >= -0.02) & (feat_df['price_change_1min'] < -0.01)),
    ('Dropped 0-1%', (feat_df['price_change_1min'] >= -0.01) & (feat_df['price_change_1min'] < 0)),
    ('Flat/Up', feat_df['price_change_1min'] >= 0),
]:
    sub = feat_df[cond]
    if len(sub) > 0:
        print(f'  {label:15s}: {len(sub):4d} trades | WR={( sub["pnl"]>0).mean()*100:.1f}% | AvgPnL={sub["pnl"].mean()*100:.2f}%')

# 2. Drop in first 5 min
print('\n--- Drop in first 5 min ---')
for label, cond in [
    ('Dropped >3%', feat_df['drop_5min'] > 0.03),
    ('Dropped 2-3%', (feat_df['drop_5min'] >= 0.02) & (feat_df['drop_5min'] < 0.03)),
    ('Dropped 1-2%', (feat_df['drop_5min'] >= 0.01) & (feat_df['drop_5min'] < 0.02)),
    ('Dropped 0-1%', (feat_df['drop_5min'] >= 0) & (feat_df['drop_5min'] < 0.01)),
]:
    sub = feat_df[cond]
    if len(sub) > 0:
        print(f'  {label:15s}: {len(sub):4d} trades | WR={(sub["pnl"]>0).mean()*100:.1f}% | AvgPnL={sub["pnl"].mean()*100:.2f}%')

# 3. Volume ratio
print('\n--- Volume in first 5 min / total day volume ---')
for label, cond in [
    ('<10%', feat_df['vol_ratio_5'] < 0.10),
    ('10-20%', (feat_df['vol_ratio_5'] >= 0.10) & (feat_df['vol_ratio_5'] < 0.20)),
    ('20-30%', (feat_df['vol_ratio_5'] >= 0.20) & (feat_df['vol_ratio_5'] < 0.30)),
    ('30-50%', (feat_df['vol_ratio_5'] >= 0.30) & (feat_df['vol_ratio_5'] < 0.50)),
    ('>50%', feat_df['vol_ratio_5'] >= 0.50),
]:
    sub = feat_df[cond]
    if len(sub) > 0:
        print(f'  {label:15s}: {len(sub):4d} trades | WR={(sub["pnl"]>0).mean()*100:.1f}% | AvgPnL={sub["pnl"].mean()*100:.2f}%')

# 4. Sell ratio
print('\n--- Sell volume ratio (first 5 min) ---')
for label, cond in [
    ('>70%', feat_df['sell_ratio'] > 0.70),
    ('60-70%', (feat_df['sell_ratio'] >= 0.60) & (feat_df['sell_ratio'] < 0.70)),
    ('50-60%', (feat_df['sell_ratio'] >= 0.50) & (feat_df['sell_ratio'] < 0.60)),
    ('<50%', feat_df['sell_ratio'] < 0.50),
]:
    sub = feat_df[cond]
    if len(sub) > 0:
        print(f'  {label:15s}: {len(sub):4d} trades | WR={(sub["pnl"]>0).mean()*100:.1f}% | AvgPnL={sub["pnl"].mean()*100:.2f}%')

# 5. Gap size
print('\n--- Gap size (adj_gap) ---')
for label, cond in [
    ('>10%', feat_df['adj_gap'] > 0.10),
    ('7-10%', (feat_df['adj_gap'] >= 0.07) & (feat_df['adj_gap'] < 0.10)),
    ('5-7%', (feat_df['adj_gap'] >= 0.05) & (feat_df['adj_gap'] < 0.07)),
]:
    sub = feat_df[cond]
    if len(sub) > 0:
        print(f'  {label:15s}: {len(sub):4d} trades | WR={(sub["pnl"]>0).mean()*100:.1f}% | AvgPnL={sub["pnl"].mean()*100:.2f}%')

# 6. COMBINED FILTERS
print(f'\n{"=" * 70}')
print('COMBINED FILTERS')
print(f'{"=" * 70}')

combos = [
    ('Drop>1% + Vol<30%', (feat_df['drop_5min'] > 0.01) & (feat_df['vol_ratio_5'] < 0.30)),
    ('Drop>1% + Sell>60%', (feat_df['drop_5min'] > 0.01) & (feat_df['sell_ratio'] > 0.60)),
    ('Drop>2% + Vol<20%', (feat_df['drop_5min'] > 0.02) & (feat_df['vol_ratio_5'] < 0.20)),
    ('Drop>2% + Sell>60%', (feat_df['drop_5min'] > 0.02) & (feat_df['sell_ratio'] > 0.60)),
    ('Drop>1% + Vol<30% + Gap>7%', (feat_df['drop_5min'] > 0.01) & (feat_df['vol_ratio_5'] < 0.30) & (feat_df['adj_gap'] > 0.07)),
    ('Drop>2% + Vol<20% + Gap>7%', (feat_df['drop_5min'] > 0.02) & (feat_df['vol_ratio_5'] < 0.20) & (feat_df['adj_gap'] > 0.07)),
]

for label, cond in combos:
    sub = feat_df[cond]
    if len(sub) > 0:
        print(f'  {label:35s}: {len(sub):4d} trades | WR={(sub["pnl"]>0).mean()*100:.1f}% | AvgPnL={sub["pnl"].mean()*100:.2f}%')
