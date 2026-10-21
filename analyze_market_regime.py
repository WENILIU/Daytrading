import pandas as pd
import numpy as np

sigs = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")

def calc_pnl(row):
    entry = row['entry']
    direction = row['direction']
    sl_pct, tp_pct = 0.06, 0.04
    if direction == 'SHORT':
        sl_price = entry * (1 + sl_pct)
        tp_price = entry * (1 - tp_pct)
        hit_tp = row['day_low'] <= tp_price
        hit_sl = row['day_high'] >= sl_price
        if hit_tp and hit_sl:
            return tp_pct if row['day_close'] < entry else -sl_pct
        elif hit_tp: return tp_pct
        elif hit_sl: return -sl_pct
        else: return (entry - row['day_close']) / entry
    else:
        sl_price = entry * (1 - sl_pct)
        tp_price = entry * (1 + tp_pct)
        hit_tp = row['day_high'] >= tp_price
        hit_sl = row['day_low'] <= sl_price
        if hit_tp and hit_sl:
            return tp_pct if row['day_close'] > entry else -sl_pct
        elif hit_tp: return tp_pct
        elif hit_sl: return -sl_pct
        else: return (row['day_close'] - entry) / entry

sigs['pnl'] = sigs.apply(calc_pnl, axis=1)
sigs['abs_gap'] = sigs['adj_gap'].abs()
sigs['win'] = (sigs['pnl'] > 0).astype(int)

# Top 15 per day
sigs_sorted = sigs.sort_values(['date', 'abs_gap'], ascending=[True, False])
sigs_top = sigs_sorted.groupby('date').head(15).copy()

# Build daily market stats from signals
daily = sigs_top.groupby('date').agg(
    market_ret=('market_ret', 'first'),
    avg_pnl=('pnl', 'mean'),
    win_rate=('win', 'mean'),
    count=('pnl', 'count'),
    total_pnl=('pnl', 'sum'),
).reset_index()
daily['date'] = pd.to_datetime(daily['date'])
daily = daily.sort_values('date').reset_index(drop=True)

# Calculate market position indicators
# Use the daily market_ret to reconstruct market index
daily['market_index'] = (1 + daily['market_ret']).cumprod()

# Rolling stats
daily['ma5'] = daily['market_index'].rolling(5).mean()
daily['ma20'] = daily['market_index'].rolling(20).mean()
daily['ma60'] = daily['market_index'].rolling(60).mean()
daily['ma120'] = daily['market_index'].rolling(120).mean()

# Position relative to MAs
daily['above_ma5'] = (daily['market_index'] > daily['ma5']).astype(int)
daily['above_ma20'] = (daily['market_index'] > daily['ma20']).astype(int)
daily['above_ma60'] = (daily['market_index'] > daily['ma60']).astype(int)
daily['above_ma120'] = (daily['market_index'] > daily['ma120']).astype(int)

# Distance from recent high/low
daily['high_20'] = daily['market_index'].rolling(20).max()
daily['low_20'] = daily['market_index'].rolling(20).min()
daily['high_60'] = daily['market_index'].rolling(60).max()
daily['low_60'] = daily['market_index'].rolling(60).min()
daily['pct_from_high20'] = (daily['market_index'] - daily['high_20']) / daily['high_20']
daily['pct_from_high60'] = (daily['market_index'] - daily['high_60']) / daily['high_60']
daily['pct_from_low20'] = (daily['market_index'] - daily['low_20']) / daily['low_20']

# Volatility
daily['vol_5'] = daily['market_ret'].rolling(5).std()
daily['vol_20'] = daily['market_ret'].rolling(20).std()

# Consecutive direction
daily['up_streak'] = 0
for i in range(1, len(daily)):
    if daily.iloc[i]['market_ret'] > 0:
        daily.iloc[i, daily.columns.get_loc('up_streak')] = max(0, daily.iloc[i-1]['up_streak'] + 1)
    elif daily.iloc[i]['market_ret'] < 0:
        daily.iloc[i, daily.columns.get_loc('up_streak')] = min(0, daily.iloc[i-1]['up_streak'] - 1)

# Merge back to signals
sigs_top['date_dt'] = pd.to_datetime(sigs_top['date'])
merged = sigs_top.merge(daily, left_on='date_dt', right_on='date', how='left', suffixes=('', '_daily'))

# Drop rows without enough history
merged = merged.dropna(subset=['ma20', 'vol_20'])

print("=" * 80)
print("MARKET REGIME ANALYSIS")
print("=" * 80)

# 1. Market position relative to MA20
print("\n--- 1. 大盤相對 MA20 位置 ---")
merged['ma20_pos'] = np.where(merged['market_index'] > merged['ma20'], 'Above MA20', 'Below MA20')
for pos, grp in merged.groupby('ma20_pos'):
    print(f"  {pos:<15}: {len(grp):>6} trades, WR={grp['win'].mean()*100:.1f}%, avg={grp['pnl'].mean()*100:.2f}%")

# 2. Market position relative to MA60
print("\n--- 2. 大盤相對 MA60 位置 ---")
merged['ma60_pos'] = np.where(merged['market_index'] > merged['ma60'], 'Above MA60', 'Below MA60')
for pos, grp in merged.groupby('ma60_pos'):
    print(f"  {pos:<15}: {len(grp):>6} trades, WR={grp['win'].mean()*100:.1f}%, avg={grp['pnl'].mean()*100:.2f}%")

# 3. Distance from 20-day high
print("\n--- 3. 距 20 日高點距離 ---")
bins = [-1, -0.05, -0.03, -0.01, 0, 1]
labels = ['<-5%', '-5~-3%', '-3~-1%', '-1~0%', 'At high']
merged['from_high'] = pd.cut(merged['pct_from_high20'], bins=bins, labels=labels)
for pos, grp in merged.groupby('from_high', observed=True):
    print(f"  {str(pos):<10}: {len(grp):>6} trades, WR={grp['win'].mean()*100:.1f}%, avg={grp['pnl'].mean()*100:.2f}%")

# 4. Market volatility
print("\n--- 4. 大盤波動率 (5日std) ---")
vol_q = merged['vol_5'].quantile([0.2, 0.4, 0.6, 0.8]).values
merged['vol_bucket'] = pd.cut(merged['vol_5'], bins=[0]+list(vol_q)+[99], 
                              labels=['Low(V1)', 'Low-Mid(V2)', 'Mid(V3)', 'High(V4)', 'VeryHigh(V5)'])
for pos, grp in merged.groupby('vol_bucket', observed=True):
    print(f"  {str(pos):<15}: {len(grp):>6} trades, WR={grp['win'].mean()*100:.1f}%, avg={grp['pnl'].mean()*100:.2f}%")

# 5. Market gap direction (today's market open)
print("\n--- 5. 大盤當日 gap (market_ret) ---")
bins = [-1, -0.02, -0.01, 0, 0.01, 0.02, 1]
labels = ['跌>2%', '跌1-2%', '跌0-1%', '漲0-1%', '漲1-2%', '漲>2%']
merged['mkt_gap'] = pd.cut(merged['market_ret'], bins=bins, labels=labels)
for pos, grp in merged.groupby('mkt_gap', observed=True):
    print(f"  {str(pos):<10}: {len(grp):>6} trades, WR={grp['win'].mean()*100:.1f}%, avg={grp['pnl'].mean()*100:.2f}%")

# 6. Consecutive up/down days
print("\n--- 6. 大盤連續漲跌天數 ---")
merged['streak_bucket'] = pd.cut(merged['up_streak'], bins=[-10,-3,-1,0,1,3,10],
                                  labels=['跌>3天', '跌2-3天', '跌1天', '平', '漲1天', '漲>1天'])
for pos, grp in merged.groupby('streak_bucket', observed=True):
    print(f"  {str(pos):<10}: {len(grp):>6} trades, WR={grp['win'].mean()*100:.1f}%, avg={grp['pnl'].mean()*100:.2f}%")

# 7. COMBINED: Best and worst conditions
print("\n--- 7. 最佳/最差組合 ---")
# Best: Below MA20 + high vol + market down
best = merged[(merged['market_index'] < merged['ma20']) & (merged['market_ret'] < -0.01)]
worst = merged[(merged['market_index'] > merged['ma20']) & (merged['market_ret'] > 0.01)]
print(f"  Best (Below MA20 + 大盤跌): {len(best):>5} trades, WR={best['win'].mean()*100:.1f}%, avg={best['pnl'].mean()*100:.2f}%")
print(f"  Worst (Above MA20 + 大盤漲): {len(worst):>5} trades, WR={worst['win'].mean()*100:.1f}%, avg={worst['pnl'].mean()*100:.2f}%")

# 8. By direction
print("\n--- 8. SHORT vs LONG 在不同環境 ---")
for d in ['SHORT', 'LONG']:
    subset = merged[merged['direction'] == d]
    print(f"\n  {d}:")
    for pos, grp in subset.groupby('ma20_pos'):
        print(f"    {pos:<15}: {len(grp):>6} trades, WR={grp['win'].mean()*100:.1f}%, avg={grp['pnl'].mean()*100:.2f}%")
    for pos, grp in subset.groupby('mkt_gap', observed=True):
        print(f"    大盤{str(pos):<8}: {len(grp):>6} trades, WR={grp['win'].mean()*100:.1f}%, avg={grp['pnl'].mean()*100:.2f}%")
