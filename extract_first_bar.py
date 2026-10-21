"""
Extract first 1-min bar features (9:00-9:01) and test predictive power.
Entry penalty is minimal (only 1 min of price movement).
"""
import pandas as pd, numpy as np, json, time, os
from pathlib import Path
from collections import defaultdict

with open('stock_path_index.json','r',encoding='utf-8') as f:
    INDEX = json.load(f)

# Load signals with features already (reuse volume_features for join)
feat_df = pd.read_csv('volume_features.csv', parse_dates=['date'])
feat_df['date_str'] = feat_df['date'].dt.strftime('%Y-%m-%d')

# Group by stock for file access
stock_groups = defaultdict(list)
for idx, row in feat_df.iterrows():
    stock_groups[row['stock']].append(idx)

print(f"Stocks to process: {len(stock_groups)}")

def extract_first_bar(bars_by_date, target_date, prev_date):
    """Extract first 1-min bar features."""
    if target_date not in bars_by_date:
        return None
    
    today_bars = sorted(bars_by_date[target_date], key=lambda x: x.get('date',''))
    if not today_bars:
        return None
    
    # First bar (9:00)
    bar1 = today_bars[0]
    bar1_time = bar1.get('date','')[11:16]
    if bar1_time != '09:00':
        # First bar might be 09:01 if 09:00 is missing
        pass
    
    # First 1 min: bars with time < 09:01
    first1 = [b for b in today_bars if b.get('date','')[11:16] < '09:01']
    if not first1:
        first1 = [today_bars[0]]  # use whatever is first
    
    # First 2 min
    first2 = [b for b in today_bars if b.get('date','')[11:16] < '09:02']
    
    # First 3 min
    first3 = [b for b in today_bars if b.get('date','')[11:16] < '09:03']
    
    open_price = today_bars[0].get('open', 0)
    if open_price == 0:
        return None
    
    # First bar close
    close_1min = first1[-1].get('close', 0)
    high_1min = max(b.get('high', 0) for b in first1)
    low_1min = min(b.get('low', 999999) for b in first1)
    vol_1min = sum(b.get('volume', 0) for b in first1)
    
    # 2-min
    close_2min = first2[-1].get('close', 0) if first2 else close_1min
    vol_2min = sum(b.get('volume', 0) for b in first2)
    
    # 3-min
    close_3min = first3[-1].get('close', 0) if first3 else close_2min
    vol_3min = sum(b.get('volume', 0) for b in first3)
    
    # Previous day volume
    vol_prev = 0
    if prev_date and prev_date in bars_by_date:
        vol_prev = sum(b.get('volume', 0) for b in bars_by_date[prev_date])
    
    # Today total volume (for concentration calc)
    vol_today = sum(b.get('volume', 0) for b in today_bars)
    
    if vol_prev == 0:
        return None
    
    return {
        'price_chg_1min': (close_1min - open_price) / open_price,
        'price_chg_2min': (close_2min - open_price) / open_price,
        'price_chg_3min': (close_3min - open_price) / open_price,
        'bar1_range': (high_1min - low_1min) / open_price,
        'vol_1min': vol_1min,
        'vol_2min': vol_2min,
        'vol_3min': vol_3min,
        'vol_1min_vs_prev': vol_1min / vol_prev,
        'vol_2min_vs_prev': vol_2min / vol_prev,
        'vol_3min_vs_prev': vol_3min / vol_prev,
        'vol_1min_conc': vol_1min / vol_today if vol_today > 0 else 0,
        'entry_1min': close_1min,
        'entry_2min': close_2min,
        'entry_3min': close_3min,
    }

# Process
t0 = time.time()
all_results = []
processed = 0

for stock, indices in stock_groups.items():
    folder = INDEX.get(stock)
    if not folder or not os.path.isdir(folder):
        continue
    
    # Load all bars for this stock
    all_by_date = defaultdict(list)
    for fname in sorted(os.listdir(folder)):
        if not fname.endswith('.json'):
            continue
        parts = fname.replace('.json','').split('_')
        if len(parts) == 2 and len(parts[1]) == 10:
            continue  # skip daily files
        fpath = os.path.join(folder, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            if not isinstance(raw, dict) or 'data' not in raw:
                continue
            for b in raw['data']:
                d = b.get('date','')[:10]
                if d:
                    all_by_date[d].append(b)
        except:
            continue
    
    if not all_by_date:
        continue
    
    sorted_dates = sorted(all_by_date.keys())
    
    for idx in indices:
        row = feat_df.loc[idx]
        date_str = row['date_str']
        if date_str not in all_by_date:
            continue
        
        prev_dates = [d for d in sorted_dates if d < date_str]
        prev_date = prev_dates[-1] if prev_dates else None
        
        feats = extract_first_bar(all_by_date, date_str, prev_date)
        if feats is None:
            continue
        
        all_results.append({'idx': idx, **feats})
    
    processed += 1
    if processed % 100 == 0:
        print(f"  {processed}/{len(stock_groups)} stocks, {len(all_results)} results, {time.time()-t0:.0f}s")

print(f"\nDone: {len(all_results)} results in {time.time()-t0:.0f}s")

# Merge back
result_df = pd.DataFrame(all_results)
merged = feat_df.merge(result_df, left_index=True, right_on='idx', how='left')
merged.to_csv('first_bar_features.csv', index=False, encoding='utf-8-sig')
print(f"Saved first_bar_features.csv: {merged.shape}")
