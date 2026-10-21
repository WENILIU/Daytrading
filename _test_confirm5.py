import pandas as pd
import numpy as np
import pickle
import json
import os
from pathlib import Path
from collections import defaultdict

# Load index
with open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_1min_index.pkl', 'rb') as f:
    stock_index = pickle.load(f)

# Config
SL = 0.06
TP = 0.04
COST = 0.0023
GAP_THRESHOLD = 0.05
MIN_PRICE = 30
MAX_PRICE = 225

confirm_minutes = list(range(1, 31))
results = {m: [] for m in confirm_minutes}

total_signals = 0
processed_stocks = 0
total_stocks = len(stock_index)

print(f"Scanning {total_stocks} stocks...")

for stock, folder in stock_index.items():
    processed_stocks += 1
    if processed_stocks % 300 == 0:
        print(f"  Stocks: {processed_stocks}/{total_stocks}, signals: {total_signals}")

    # Load ALL 1-min data for this stock (all files)
    try:
        files = sorted(os.listdir(folder))
    except Exception:
        continue

    # Collect all bars grouped by date
    all_day_bars = defaultdict(list)

    for fname in files:
        if not fname.endswith('.json'):
            continue
        fpath = os.path.join(folder, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            bars = data.get('data', [])
            for bar in bars:
                try:
                    d = bar['date'][:10]
                    all_day_bars[d].append(bar)
                except Exception:
                    continue
        except Exception:
            continue

    if not all_day_bars:
        continue

    # Sort dates
    sorted_dates = sorted(all_day_bars.keys())

    # For each date, use previous date's last close as prev_close
    for i in range(1, len(sorted_dates)):
        date_str = sorted_dates[i]
        prev_date = sorted_dates[i - 1]

        if date_str < '2023-05-01' or date_str > '2026-01-31':
            continue

        # Get prev close from previous day's last bar
        prev_bars = all_day_bars[prev_date]
        if not prev_bars:
            continue
        prev_bars.sort(key=lambda b: b['date'])
        prev_close = prev_bars[-1]['close']
        if prev_close <= 0:
            continue

        # Get today's bars
        day_bars = all_day_bars[date_str]
        if not day_bars:
            continue
        day_bars.sort(key=lambda b: b['date'])

        # Get 9:00 open
        first_bar = day_bars[0]
        try:
            open_time = first_bar['date'].split('T')[1][:5]
            if open_time > '09:01':
                continue
            open_price = first_bar['open']
        except Exception:
            continue

        if open_price < MIN_PRICE or open_price > MAX_PRICE:
            continue

        # Gap check
        raw_gap = (open_price - prev_close) / prev_close
        if raw_gap < GAP_THRESHOLD:
            continue

        total_signals += 1

        # Build arrays
        bar_times = []
        bar_highs = []
        bar_lows = []
        bar_closes = []
        for bar in day_bars:
            try:
                t = bar['date'].split('T')[1][:5]
                bar_times.append(t)
                bar_highs.append(bar['high'])
                bar_lows.append(bar['low'])
                bar_closes.append(bar['close'])
            except Exception:
                continue

        if not bar_times:
            continue

        # Test each confirmation minute
        for m in confirm_minutes:
            confirm_time = f"09:{m:02d}"
            if confirm_time not in bar_times:
                continue
            ci = bar_times.index(confirm_time)
            price_at_confirm = bar_closes[ci]
            if price_at_confirm <= 0:
                continue

            drop_pct = (open_price - price_at_confirm) / open_price
            if drop_pct <= 0:
                continue

            entry_price = price_at_confirm
            sl_price = entry_price * (1 + SL)
            tp_price = entry_price * (1 - TP)

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

print(f"\nDone. Total gap signals: {total_signals}")

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
print("\nSaved.")
