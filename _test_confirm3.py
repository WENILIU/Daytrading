import pandas as pd
import numpy as np
import pickle
import json
import os
from pathlib import Path

# Load signals
sig_path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl'
signals = pd.read_pickle(sig_path)
signals['date'] = pd.to_datetime(signals['date'])
signals = signals[(signals['date'] >= '2023-05-01') & (signals['date'] <= '2026-01-31')]
signals = signals[signals['direction'] == 'SHORT']

# Load index
with open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_1min_index.pkl', 'rb') as f:
    stock_index = pickle.load(f)

# Config
SL = 0.06
TP = 0.04
COST = 0.0023

# Cache for monthly files (avoid re-reading same file)
month_cache = {}

def load_bars(stock, date_str, folder):
    """Load 1-min bars for a stock on a specific date. Handles both daily and monthly files."""
    # Try daily file first
    daily_path = os.path.join(folder, f"{stock}_{date_str}.json")
    if os.path.exists(daily_path):
        try:
            with open(daily_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('data', [])
        except Exception:
            return []

    # Try monthly file
    month_str = date_str[:7]  # "2023-05"
    cache_key = f"{stock}_{month_str}"
    if cache_key in month_cache:
        bars = month_cache[cache_key]
    else:
        monthly_path = os.path.join(folder, f"{stock}_{month_str}.json")
        if not os.path.exists(monthly_path):
            return []
        try:
            with open(monthly_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            bars = data.get('data', [])
            month_cache[cache_key] = bars
        except Exception:
            return []

    # Filter to specific date
    filtered = [b for b in bars if b.get('date', '').startswith(date_str)]
    return filtered

# Test each confirmation minute
confirm_minutes = list(range(1, 31))
results = {m: [] for m in confirm_minutes}

total = len(signals)
print(f"Testing {total} SHORT signals, minutes 9:01-9:30...")

processed = 0
found_data = 0

for idx, sig in signals.iterrows():
    processed += 1
    if processed % 1000 == 0:
        print(f"  Progress: {processed}/{total}, found data: {found_data}")

    stock = str(sig['stock'])
    date_str = sig['date'].strftime('%Y-%m-%d')
    open_price = sig['entry']

    folder = stock_index.get(stock)
    if not folder:
        continue

    bars = load_bars(stock, date_str, folder)
    if not bars:
        continue

    found_data += 1

    # Parse bars
    bar_times = []
    bar_highs = []
    bar_lows = []
    bar_closes = []

    for bar in bars:
        try:
            time_str = bar['date'].split('T')[1][:5]
            bar_times.append(time_str)
            bar_highs.append(bar['high'])
            bar_lows.append(bar['low'])
            bar_closes.append(bar['close'])
        except Exception:
            continue

    if not bar_times:
        continue

    # For each confirmation minute
    for m in confirm_minutes:
        confirm_time = f"09:{m:02d}"

        if confirm_time not in bar_times:
            continue
        ci = bar_times.index(confirm_time)
        price_at_confirm = bar_closes[ci]

        if price_at_confirm <= 0:
            continue

        # Check confirmation: price dropped from open
        drop_pct = (open_price - price_at_confirm) / open_price
        if drop_pct <= 0:
            continue

        # Entry
        entry_price = price_at_confirm
        sl_price = entry_price * (1 + SL)
        tp_price = entry_price * (1 - TP)

        # Simulate using bars AFTER entry
        pnl = None
        for j in range(ci + 1, len(bar_times)):
            if bar_times[j] >= "13:25":
                pnl = (entry_price - bar_closes[j]) / entry_price
                break
            if bar_highs[j] >= sl_price:
                pnl = -SL
                break
            if bar_lows[j] <= tp_price:
                pnl = TP
                break

        if pnl is None:
            if bar_closes:
                pnl = (entry_price - bar_closes[-1]) / entry_price
            else:
                continue

        pnl -= COST

        results[m].append({
            'date': date_str, 'stock': stock,
            'confirm_minute': m, 'drop_pct': drop_pct,
            'entry': entry_price, 'pnl': pnl,
        })

print(f"\nDone. Found data for {found_data}/{total} signals ({found_data/total*100:.1f}%)")

# Aggregate
print("\n" + "=" * 75)
print(f"{'Time':<6} {'Trades':>7} {'WinRate':>8} {'AvgPnL':>8} {'TotalPnL':>9} {'MaxDD':>8} {'Sharpe':>7}")
print("-" * 75)

summary = []
for m in confirm_minutes:
    trades = results[m]
    if not trades:
        continue
    df = pd.DataFrame(trades)
    n = len(df)
    wr = (df['pnl'] > 0).mean() * 100
    avg = df['pnl'].mean() * 100
    total_pnl = df['pnl'].sum() * 100
    std = df['pnl'].std()
    sharpe = (df['pnl'].mean() / std * np.sqrt(252)) if std > 0 else 0

    cum = df['pnl'].cumsum()
    dd = (cum - cum.cummax()).min() * 100

    summary.append({
        'minute': m, 'trades': n, 'winrate': wr,
        'avg_pnl': avg, 'total_pnl': total_pnl,
        'max_dd': dd, 'sharpe': sharpe
    })
    print(f"9:{m:02d}  {n:>7} {wr:>7.1f}% {avg:>7.3f}% {total_pnl:>8.1f}% {dd:>7.1f}% {sharpe:>7.2f}")

pd.DataFrame(summary).to_csv(
    r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\confirm_time_test.csv',
    index=False, encoding='utf-8-sig')
print("\nSaved to confirm_time_test.csv")
