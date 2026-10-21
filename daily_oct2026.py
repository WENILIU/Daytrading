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

def kelly_tier(abs_gap):
    if abs_gap > 0.09: return 2.5
    if abs_gap > 0.08: return 2.0
    if abs_gap > 0.07: return 1.8
    if abs_gap > 0.065: return 1.5
    if abs_gap > 0.06: return 1.2
    return 1.0

# Filter October 2026
sigs['date_dt'] = pd.to_datetime(sigs['date'])
oct2026 = sigs[(sigs['date_dt'] >= '2026-10-01') & (sigs['date_dt'] <= '2026-10-31')].copy()

# Top 15 per day
oct2026 = oct2026.sort_values(['date', 'abs_gap'], ascending=[True, False])
oct2026 = oct2026.groupby('date').head(15).copy()

# Simulate with 整張
CAPITAL = 4_500_000
COST = 0.0017

results = []
for date, day in oct2026.groupby('date'):
    day = day.copy()
    day['tier'] = day['abs_gap'].apply(kelly_tier)
    day = day.sort_values('abs_gap', ascending=False)
    
    available = CAPITAL * 0.70
    day_pnl = 0
    trades = []
    
    for _, trade in day.iterrows():
        target_val = CAPITAL * 0.05 * trade['tier']
        entry_price = trade['entry']
        if entry_price <= 0: continue
        lots = int(target_val / (entry_price * 1000))
        if lots < 1: continue
        shares = lots * 1000
        pos_val = shares * entry_price
        if pos_val > available:
            lots = int(available / (entry_price * 1000))
            if lots < 1: continue
            shares = lots * 1000
            pos_val = shares * entry_price
        available -= pos_val
        
        net_pnl_pct = trade['pnl'] - COST
        net_pnl_dollar = pos_val * net_pnl_pct
        day_pnl += net_pnl_dollar
        
        trades.append({
            'symbol': trade['stock'],
            'direction': trade['direction'],
            'entry': entry_price,
            'shares': shares,
            'tier': trade['tier'],
            'gap': trade['adj_gap'],
            'pnl_pct': net_pnl_pct,
            'pnl_dollar': net_pnl_dollar,
        })
        
        if available <= 0: break
    
    results.append({
        'date': date,
        'day_pnl': day_pnl,
        'day_ret': day_pnl / CAPITAL,
        'trades': len(trades),
        'trade_details': trades,
    })

# Print
print("=" * 90)
print("2026年10月 每日績效 (Kelly 6-tier, 450萬, 整張)")
print("=" * 90)
print(f"\n{'日期':<12} {'筆數':>4} {'當日損益':>12} {'當日報酬':>8} {'累計損益':>12} {'累計報酬':>8}")
print("-" * 70)

cum_pnl = 0
cum_ret = 1.0
for r in results:
    cum_pnl += r['day_pnl']
    cum_ret *= (1 + r['day_ret'])
    date_str = str(r['date'])[:10]
    print(f"{date_str:<12} {r['trades']:>4} {r['day_pnl']:>+12,.0f} {r['day_ret']*100:>+7.2f}% {cum_pnl:>+12,.0f} {(cum_ret-1)*100:>+7.2f}%")

print("-" * 70)
print(f"{'合計':<12} {sum(r['trades'] for r in results):>4} {cum_pnl:>+12,.0f} {'':>8} {'':>12} {(cum_ret-1)*100:>+7.2f}%")

# Detailed trades for each day
print(f"\n{'='*90}")
print("每日交易明細")
print(f"{'='*90}")

for r in results:
    if r['trades'] == 0:
        continue
    date_str = str(r['date'])[:10]
    print(f"\n--- {date_str} ({r['trades']} trades, PnL: {r['day_pnl']:+,.0f}) ---")
    print(f"  {'股票':<6} {'方向':<6} {'進場':>8} {'張數':>5} {'Tier':>5} {'Gap':>7} {'PnL%':>7} {'PnL$':>10}")
    for t in r['trade_details']:
        lots = t['shares'] // 1000
        print(f"  {t['symbol']:<6} {t['direction']:<6} {t['entry']:>8.2f} {lots:>5} {t['tier']:>5.1f} {t['gap']*100:>+6.1f}% {t['pnl_pct']*100:>+6.2f}% {t['pnl_dollar']:>+10,.0f}")
