import pandas as pd
import numpy as np

sigs = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")

# Show concrete examples with different market conditions
# adj_gap = raw_gap - market_gap
# So: raw_gap = adj_gap + market_gap

print("=" * 80)
print("實際例子：adj_gap = 5% 在不同大盤環境下的真實股價")
print("=" * 80)

# Case 1: Market flat (market_gap = 0)
# Case 2: Market up (market_gap = +3%)  
# Case 3: Market down (market_gap = -3%)

print("""
假設：某股票前收盤 = 100 元，adj_gap = +5%（SHORT 訊號）

┌─────────────────────────────────────────────────────────────────┐
│ 情境 A: 大盤平盤 (market_gap = 0%)                              │
│   raw_gap = 5% + 0% = 5%                                       │
│   開盤價 = 100 × 1.05 = 105 元 ← 進場                         │
│   停損 = 105 × 1.06 = 111.3 元                                 │
│   漲停 = 100 × 1.10 = 110 元                                   │
│   → 停損(111.3) > 漲停(110) → 停損到不了 ✓ 安全               │
│   → 最大虧損 = (110-105)/105 = 4.76%                          │
├─────────────────────────────────────────────────────────────────┤
│ 情境 B: 大盤上漲 (market_gap = +3%)                             │
│   raw_gap = 5% + 3% = 8%                                       │
│   開盤價 = 100 × 1.08 = 108 元 ← 進場                         │
│   停損 = 108 × 1.06 = 114.5 元                                 │
│   漲停 = 100 × 1.10 = 110 元                                   │
│   → 停損(114.5) > 漲停(110) → 停損到不了 ✓ 更安全             │
│   → 最大虧損 = (110-108)/108 = 1.85%  ← 大盤漲反而保護你！    │
├─────────────────────────────────────────────────────────────────┤
│ 情境 C: 大盤下跌 (market_gap = -3%)                             │
│   raw_gap = 5% + (-3%) = 2%                                    │
│   開盤價 = 100 × 1.02 = 102 元 ← 進場                         │
│   停損 = 102 × 1.06 = 108.1 元                                 │
│   漲停 = 100 × 1.10 = 110 元                                   │
│   → 停損(108.1) < 漲停(110) → 停損可以觸發！ ⚠️              │
│   → 最大虧損 = 6%（停損正常運作）                              │
└─────────────────────────────────────────────────────────────────┘

結論：
- 大盤漲或平盤 → 停損到不了，漲停保護你（虧損 < 6%）
- 大盤跌 → 個股 raw_gap 小，停損可能觸發（虧損 = 6%）
- 最壞情況就是停損正常觸發 = 虧 6%，不會超過
""")

# Now show actual data distribution
print("=" * 80)
print("實際數據分佈：adj_gap=5% 時的 raw_gap 分佈")
print("=" * 80)

sigs['abs_adj_gap'] = sigs['adj_gap'].abs()
sigs['raw_gap_abs'] = sigs['raw_gap'].abs() if 'raw_gap' in sigs.columns else None

# Check what columns we have
print(f"\nAvailable columns: {list(sigs.columns)}")

# Filter SHORT signals with adj_gap around 5%
short_5 = sigs[(sigs['adj_gap'] >= 0.05) & (sigs['adj_gap'] < 0.06)].copy()
print(f"\nSHORT signals with adj_gap 5-6%: {len(short_5)} trades")

if 'market_ret' in short_5.columns:
    # market_ret is the market return that day
    # raw_gap = adj_gap + market_ret (approximately)
    short_5['estimated_raw_gap'] = short_5['adj_gap'] + short_5['market_ret']
    
    print(f"\n  Raw gap distribution (estimated):")
    print(f"  Mean raw_gap: {short_5['estimated_raw_gap'].mean()*100:.2f}%")
    print(f"  Min raw_gap: {short_5['estimated_raw_gap'].min()*100:.2f}%")
    print(f"  Max raw_gap: {short_5['estimated_raw_gap'].max()*100:.2f}%")
    
    # When is SL reachable? raw_gap < 3.77%
    sl_reachable = short_5['estimated_raw_gap'] < 0.0377
    print(f"\n  SL reachable (raw_gap < 3.77%): {sl_reachable.sum()} ({sl_reachable.mean()*100:.1f}%)")
    print(f"  SL unreachable (raw_gap > 3.77%): {(~sl_reachable).sum()} ({(~sl_reachable).mean()*100:.1f}%)")
    
    # Market conditions
    print(f"\n  Market conditions when signal fires:")
    print(f"  Market up >2%: {(short_5['market_ret'] > 0.02).sum()} ({(short_5['market_ret'] > 0.02).mean()*100:.1f}%)")
    print(f"  Market -2% to +2%: {((short_5['market_ret'] >= -0.02) & (short_5['market_ret'] <= 0.02)).sum()}")
    print(f"  Market down >2%: {(short_5['market_ret'] < -0.02).sum()} ({(short_5['market_ret'] < -0.02).mean()*100:.1f}%)")
    
    # PnL by market condition
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
    
    short_5['pnl'] = short_5.apply(calc_pnl, axis=1)
    
    print(f"\n  PnL by market condition:")
    for label, mask in [
        ("大盤漲>2%", short_5['market_ret'] > 0.02),
        ("大盤平", (short_5['market_ret'] >= -0.02) & (short_5['market_ret'] <= 0.02)),
        ("大盤跌>2%", short_5['market_ret'] < -0.02),
    ]:
        subset = short_5[mask]
        if len(subset) > 0:
            print(f"    {label:<12}: {len(subset):>5} trades, WR={((subset['pnl']>0).mean()*100):.1f}%, avg={subset['pnl'].mean()*100:.2f}%, worst={subset['pnl'].min()*100:.1f}%")
