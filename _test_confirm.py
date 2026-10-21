import pandas as pd
import numpy as np
import pickle
import json
import os
from pathlib import Path
from datetime import datetime

# Load signals
sig_path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl'
signals = pd.read_pickle(sig_path)
signals['date'] = pd.to_datetime(signals['date'])
signals = signals[(signals['date'] >= '2023-05-01') & (signals['date'] <= '2026-01-31')]
signals = signals[signals['direction'] == 'SHORT']  # Focus on SHORT (main alpha)

# Load index
with open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_1min_index.pkl', 'rb') as f:
    stock_index = pickle.load(f)

# Config
SL = 0.06
TP = 0.04
COST = 0.0023

# Test each confirmation minute
confirm_minutes = list(range(1, 31))  # 9:01 to 9:30
results = {m: [] for m in confirm_minutes}

# Process signals
total = len(signals)
print(f"Testing {total} SHORT signals, minutes 9:01-9:30...")

processed = 0
skipped = 0

for idx, sig in signals.iterrows():
    processed += 1
    if processed % 500 == 0:
        print(f"  Progress: {processed}/{total}")

    stock = str(sig['stock'])
    date_str = sig['date'].strftime('%Y-%m-%d')
    open_price = sig['entry']  # This is the open price

    # Find 1-min data file
    folder = stock_index.get(stock)
    if not folder:
        skipped += 1
        continue

    filepath = os.path.join(folder, f"{stock}_{date_str}.json")
    if not os.path.exists(filepath):
        skipped += 1
        continue

    # Load 1-min data
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        bars = data['data']
    except Exception:
        skipped += 1
        continue

    if not bars:
        skipped += 1
        continue

    # Build price lookup by minute
    # Bars have format: {'date': '2025-03-26T09:01:00.000+08:00', 'open': ..., 'close': ...}
    minute_prices = {}
    day_close = 0
    day_low = float('inf')
    day_high = 0

    for bar in bars:
        try:
            bar_time = bar['date']
            # Extract HH:MM
            time_part = bar_time.split('T')[1][:5]
            minute_prices[time_part] = bar['close']
            day_close = max(day_close, 0)
            if bar['close'] > 0:
                day_close = bar['close']
            day_low = min(day_low, bar['low'])
            day_high = max(day_high, bar['high'])
        except Exception:
            continue

    if not minute_prices:
        skipped += 1
        continue

    # For each confirmation minute, check if condition is met
    for m in confirm_minutes:
        confirm_time = f"09:{m:02d}"
        price_at_confirm = minute_prices.get(confirm_time)

        if price_at_confirm is None or price_at_confirm <= 0:
            continue

        # Check confirmation: price must have dropped from open
        drop_pct = (open_price - price_at_confirm) / open_price
        if drop_pct <= 0:
            continue  # Not confirmed

        # Entry at this price
        entry_price = price_at_confirm

        # Simulate: check if SL or TP hit first (using remaining bars)
        # For simplicity, use day_high/day_low to determine outcome
        # SL: price rises 6% from entry
        # TP: price drops 4% from entry
        sl_price = entry_price * (1 + SL)
        tp_price = entry_price * (1 - TP)

        # Conservative: if day_high >= sl_price AND day_low <= tp_price, assume SL hit first
        # (pessimistic assumption)
        hit_sl = day_high >= sl_price
        hit_tp = day_low <= tp_price

        if hit_sl and hit_tp:
            # Ambiguous - use SL (conservative)
            pnl = -SL
        elif hit_sl:
            pnl = -SL
        elif hit_tp:
            pnl = TP
        else:
            # Neither hit - use day_close (force close)
            if day_close > 0:
                pnl = (entry_price - day_close) / entry_price
            else:
                pnl = 0

        # Deduct cost
        pnl -= COST

        results[m].append({
            'date': date_str,
            'stock': stock,
            'confirm_minute': m,
            'drop_pct': drop_pct,
            'entry': entry_price,
            'pnl': pnl,
        })

print(f"\nProcessed: {processed}, Skipped (no data): {skipped}")

# Aggregate results
print("\n" + "=" * 70)
print(f"{'Time':<6} {'Trades':>7} {'WinRate':>8} {'AvgPnL':>8} {'TotalPnL':>9} {'MaxDD':>8}")
print("-" * 70)

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

    # Calculate max drawdown of cumulative PnL
    cum = df['pnl'].cumsum()
    dd = (cum - cum.cummax()).min() * 100

    summary.append({
        'minute': m, 'trades': n, 'winrate': wr,
        'avg_pnl': avg, 'total_pnl': total_pnl, 'max_dd': dd
    })
    print(f"9:{m:02d}  {n:>7} {wr:>7.1f}% {avg:>7.3f}% {total_pnl:>8.1f}% {dd:>7.1f}%")

# Save results
pd.DataFrame(summary).to_csv(
    r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\confirm_time_test.csv',
    index=False, encoding='utf-8-sig')
print("\nSaved to confirm_time_test.csv")
