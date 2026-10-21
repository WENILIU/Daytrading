import pickle, os, json
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'

print('=' * 70)
print('9:05 ENTRY + 5-MIN CONFIRMATION: FULL BACKTEST')
print('=' * 70)

# Load pre-computed results for entry=5min
df_all = pd.read_pickle(f'{OUTPUT_DIR}/all_entry_sltp_results.pkl')
df = df_all[df_all['entry_min'] == 5].copy()
print(f'Entry=5min base: {len(df)} trades')

# Load 1-min data to compute 5-min features
idx = pickle.load(open(f'{OUTPUT_DIR}/stock_1min_index.pkl', 'rb'))

# Get unique stock/date pairs
pairs = df[['date', 'stock']].drop_duplicates()
print(f'Unique stock-dates: {len(pairs)}')

# Compute features
print('Computing 5-min features...')
stock_groups = pairs.groupby('stock')
feature_rows = []
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
    
    for _, row in group.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        if date_str not in day_data:
            continue
        day = day_data[date_str]
        if len(day) < 6:
            continue
        
        open_price = day[0]['open']
        first_5 = day[:5]
        
        # 5-min drop
        min_5 = min(c['low'] for c in first_5)
        drop_5min = (open_price - min_5) / open_price
        
        # Volume ratio
        vol_5 = sum(c['volume'] for c in first_5)
        vol_total = sum(c['volume'] for c in day)
        vol_ratio = vol_5 / vol_total if vol_total > 0 else 0
        
        # Sell ratio (candles where close < open)
        sell_vol = sum(c['volume'] for c in first_5 if c['close'] < c['open'])
        total_vol_5 = sum(c['volume'] for c in first_5)
        sell_ratio = sell_vol / total_vol_5 if total_vol_5 > 0 else 0.5
        
        feature_rows.append({
            'date': row['date'],
            'stock': sid,
            'drop_5min': drop_5min,
            'vol_ratio': vol_ratio,
            'sell_ratio': sell_ratio
        })
    
    del day_data
    processed += 1
    if processed % 200 == 0:
        print(f'  {processed}/{len(stock_groups)}...')

feat = pd.DataFrame(feature_rows)
print(f'Features: {len(feat)}')

# Merge features into PnL data
df = df.merge(feat, on=['date', 'stock'], how='left')
print(f'Merged: {len(df)}, features available: {df["drop_5min"].notna().sum()}')

# === FILTER + SL/TP OPTIMIZATION ===
print(f'\n{"=" * 70}')
print('FILTER EFFECTIVENESS (Entry=5min)')
print(f'{"=" * 70}')

# Test different filter thresholds with best SL/TP
# First find best SL/TP without filter
summary_base = df.groupby(['sl', 'tp']).agg(
    trades=('pnl', 'count'),
    wr=('pnl', lambda x: (x > 0).mean()),
    avg_pnl=('pnl', 'mean')
).reset_index()
best_base = summary_base[summary_base['trades'] >= 100].sort_values('avg_pnl', ascending=False).head(3)
print('\nBest SL/TP without filter:')
for _, r in best_base.iterrows():
    print(f'  SL={int(r["sl"]*100)}% TP={int(r["tp"]*100)}% | WR={r["wr"]*100:.1f}% | AvgPnL={r["avg_pnl"]*100:.2f}%')

# Now test with filters
print(f'\n--- With 5-min drop filter ---')
for drop_thresh in [0.01, 0.015, 0.02, 0.025, 0.03]:
    filtered = df[df['drop_5min'] >= drop_thresh]
    if len(filtered) < 50:
        continue
    sltp = filtered.groupby(['sl', 'tp']).agg(
        trades=('pnl', 'count'),
        wr=('pnl', lambda x: (x > 0).mean()),
        avg_pnl=('pnl', 'mean')
    ).reset_index()
    best = sltp[sltp['trades'] >= 50].sort_values('avg_pnl', ascending=False).head(1)
    if len(best) > 0:
        r = best.iloc[0]
        print(f'  Drop>={drop_thresh*100:.1f}%: {int(r["trades"]):4d} trades | SL={int(r["sl"]*100)}% TP={int(r["tp"]*100)}% | WR={r["wr"]*100:.1f}% | AvgPnL={r["avg_pnl"]*100:.2f}%')

print(f'\n--- With drop + volume filter ---')
for drop_thresh in [0.01, 0.02, 0.03]:
    for vol_thresh in [0.20, 0.30, 0.40]:
        filtered = df[(df['drop_5min'] >= drop_thresh) & (df['vol_ratio'] < vol_thresh)]
        if len(filtered) < 50:
            continue
        sltp = filtered.groupby(['sl', 'tp']).agg(
            trades=('pnl', 'count'),
            wr=('pnl', lambda x: (x > 0).mean()),
            avg_pnl=('pnl', 'mean')
        ).reset_index()
        best = sltp[sltp['trades'] >= 50].sort_values('avg_pnl', ascending=False).head(1)
        if len(best) > 0:
            r = best.iloc[0]
            print(f'  Drop>={drop_thresh*100:.0f}% Vol<{vol_thresh*100:.0f}%: {int(r["trades"]):4d} | SL={int(r["sl"]*100)}% TP={int(r["tp"]*100)}% | WR={r["wr"]*100:.1f}% | AvgPnL={r["avg_pnl"]*100:.2f}%')

print(f'\n--- With drop + sell ratio filter ---')
for drop_thresh in [0.01, 0.02, 0.03]:
    for sell_thresh in [0.50, 0.60, 0.70]:
        filtered = df[(df['drop_5min'] >= drop_thresh) & (df['sell_ratio'] >= sell_thresh)]
        if len(filtered) < 50:
            continue
        sltp = filtered.groupby(['sl', 'tp']).agg(
            trades=('pnl', 'count'),
            wr=('pnl', lambda x: (x > 0).mean()),
            avg_pnl=('pnl', 'mean')
        ).reset_index()
        best = sltp[sltp['trades'] >= 50].sort_values('avg_pnl', ascending=False).head(1)
        if len(best) > 0:
            r = best.iloc[0]
            print(f'  Drop>={drop_thresh*100:.0f}% Sell>={sell_thresh*100:.0f}%: {int(r["trades"]):4d} | SL={int(r["sl"]*100)}% TP={int(r["tp"]*100)}% | WR={r["wr"]*100:.1f}% | AvgPnL={r["avg_pnl"]*100:.2f}%')

# === PORTFOLIO BACKTEST for best combo ===
print(f'\n{"=" * 70}')
print('PORTFOLIO BACKTEST: Best filtered strategy')
print(f'{"=" * 70}')

# Use: Drop>=2% + Vol<30% + SL=5% TP=8% (or whatever is best)
# Let me find the absolute best
all_filtered = []
for drop_t in [0.01, 0.015, 0.02, 0.025, 0.03]:
    for vol_t in [0.20, 0.30, 0.40, 1.0]:
        for sell_t in [0.0, 0.50, 0.60, 0.70]:
            filtered = df.copy()
            if drop_t > 0:
                filtered = filtered[filtered['drop_5min'] >= drop_t]
            if vol_t < 1.0:
                filtered = filtered[filtered['vol_ratio'] < vol_t]
            if sell_t > 0:
                filtered = filtered[filtered['sell_ratio'] >= sell_t]
            
            if len(filtered) < 100:
                continue
            
            sltp = filtered.groupby(['sl', 'tp']).agg(
                trades=('pnl', 'count'),
                wr=('pnl', lambda x: (x > 0).mean()),
                avg_pnl=('pnl', 'mean'),
                std_pnl=('pnl', 'std')
            ).reset_index()
            sltp['sharpe'] = sltp['avg_pnl'] / sltp['std_pnl'] * np.sqrt(252)
            best = sltp[sltp['trades'] >= 100].sort_values('avg_pnl', ascending=False).head(1)
            if len(best) > 0:
                r = best.iloc[0]
                all_filtered.append({
                    'drop': drop_t, 'vol_max': vol_t, 'sell_min': sell_t,
                    'sl': r['sl'], 'tp': r['tp'],
                    'trades': int(r['trades']), 'wr': r['wr'],
                    'avg_pnl': r['avg_pnl'], 'sharpe': r['sharpe']
                })

results_df = pd.DataFrame(all_filtered).sort_values('avg_pnl', ascending=False)
print('\nTOP 10 filter+SLTP combos by AvgPnL:')
for _, r in results_df.head(10).iterrows():
    print(f'  Drop>={r["drop"]*100:.1f}% Vol<{r["vol_max"]*100:.0f}% Sell>={r["sell_min"]*100:.0f}% | '
          f'SL={int(r["sl"]*100)}% TP={int(r["tp"]*100)}% | {r["trades"]} trades | '
          f'WR={r["wr"]*100:.1f}% | AvgPnL={r["avg_pnl"]*100:.2f}% | Sharpe={r["sharpe"]:.1f}')

# Run portfolio for top 3
print(f'\n{"=" * 70}')
print('PORTFOLIO SIMULATION (top 3 strategies)')
print(f'{"=" * 70}')

CAPITAL = 4_500_000
MAX_POS = 10
MAX_EXP = 0.50
BASE_POS = 0.08

for rank, strat in results_df.head(3).iterrows():
    print(f'\n--- Strategy #{rank+1}: Drop>={strat["drop"]*100:.1f}% Vol<{strat["vol_max"]*100:.0f}% Sell>={strat["sell_min"]*100:.0f}% SL={int(strat["sl"]*100)}% TP={int(strat["tp"]*100)}% ---')
    
    filtered = df.copy()
    if strat['drop'] > 0:
        filtered = filtered[filtered['drop_5min'] >= strat['drop']]
    if strat['vol_max'] < 1.0:
        filtered = filtered[filtered['vol_ratio'] < strat['vol_max']]
    if strat['sell_min'] > 0:
        filtered = filtered[filtered['sell_ratio'] >= strat['sell_min']]
    filtered = filtered[(filtered['sl'] == strat['sl']) & (filtered['tp'] == strat['tp'])]
    filtered = filtered[(filtered['entry_price'] >= 30) & (filtered['entry_price'] <= 225)]
    
    # Position sizing
    filtered['pos_pct'] = BASE_POS
    filtered['shares'] = np.floor(filtered['pos_pct'] * CAPITAL / filtered['entry_price'] / 1000).astype(int) * 1000
    filtered = filtered[filtered['shares'] >= 1000]
    filtered['actual_pos_pct'] = (filtered['shares'] * filtered['entry_price']) / CAPITAL
    
    # Daily limits
    filtered = filtered.sort_values(['date', 'adj_gap'], ascending=[True, False])
    filtered['day_rank'] = filtered.groupby('date').cumcount()
    filtered = filtered[filtered['day_rank'] < MAX_POS]
    filtered['cum_exp'] = filtered.groupby('date')['actual_pos_pct'].cumsum()
    filtered = filtered[filtered['cum_exp'] <= MAX_EXP]
    
    if len(filtered) == 0:
        print('  No trades after filters!')
        continue
    
    filtered['dollar_pnl'] = filtered['pnl'] * filtered['actual_pos_pct'] * CAPITAL
    daily_pnl = filtered.groupby('date')['dollar_pnl'].sum()
    daily_ret = daily_pnl / CAPITAL
    
    cum = (1 + daily_ret).cumprod()
    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
    cagr = cum.iloc[-1] ** (1/years) - 1 if cum.iloc[-1] > 0 else -1
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0
    
    print(f'  Trades: {len(filtered)} | Days: {len(daily_pnl)} | Trades/day: {len(filtered)/len(daily_pnl):.1f}')
    print(f'  WR: {(filtered["pnl"]>0).mean()*100:.1f}% | AvgPnL: {filtered["pnl"].mean()*100:.2f}%')
    print(f'  CAGR: {cagr*100:.1f}% | MDD: {mdd*100:.1f}% | Sharpe: {sharpe:.1f}')
    print(f'  Total PnL: {daily_pnl.sum():,.0f}')
    
    # Annual
    for yr in sorted(daily_pnl.index.year.unique()):
        yr_pnl = daily_pnl[daily_pnl.index.year == yr]
        yr_ret = yr_pnl.sum() / CAPITAL * 100
        yr_wr = (filtered[filtered['date'].dt.year == yr]['pnl'] > 0).mean() * 100
        yr_n = len(filtered[filtered['date'].dt.year == yr])
        print(f'    {yr}: {yr_ret:+6.1f}% | WR={yr_wr:.0f}% | {yr_n} trades')
