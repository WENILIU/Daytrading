import pickle, os, json
import pandas as pd

# Load 3296 1-min data
idx = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_1min_index.pkl', 'rb'))
path = idx['3296']

# Load all data for 3296
all_data = []
files = [f for f in os.listdir(path) if f.endswith('.json')]
for f in files:
    fpath = os.path.join(path, f)
    with open(fpath, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
    if isinstance(data, dict) and 'data' in data:
        all_data.extend(data['data'])

# Group by date
days = {}
for c in all_data:
    d = c['date'][:10]
    if d not in days:
        days[d] = []
    days[d].append(c)
for d in days:
    days[d] = sorted(days[d], key=lambda x: x['date'])

# Get 10/01 close (prev_close for gap calc)
prev_day = days.get('2026-10-01', [])
prev_close = prev_day[-1]['close'] if prev_day else None

# Get 10/02 data
day = days['2026-10-02']

print('=' * 60)
print('STRATEGY VERIFICATION: 3296 on 2026-10-02')
print('=' * 60)

print(f'\n[1] Gap Signal Check:')
print(f'  Previous close (10/01): {prev_close}')
print(f'  Today open (10/02): {day[0]["open"]}')
raw_gap = (day[0]['open'] - prev_close) / prev_close
print(f'  Raw gap: {raw_gap*100:.1f}%')
print(f'  Threshold: >5% (market-adjusted)')
print(f'  Signal: {"PASS" if raw_gap > 0.05 else "FAIL"} (raw gap = {raw_gap*100:.1f}%)')

print(f'\n[2] Confirmation Check (first 15 min):')
first_15 = day[:15]
open_price = first_15[0]['open']
min_price_15 = min(c['low'] for c in first_15)
early_move = (open_price - min_price_15) / open_price
print(f'  Open price: {open_price}')
print(f'  Min price in 15 min: {min_price_15}')
print(f'  Drop from open: {early_move*100:.1f}%')
print(f'  Threshold: >=2.5%')
print(f'  Confirmation: {"PASS" if early_move >= 0.025 else "FAIL"}')

print(f'\n[3] Entry (9:15 price):')
entry = day[14]['close']
print(f'  9:14 candle close (= 9:15 price): {entry}')
print(f'  This is the ACTUAL short entry price')

print(f'\n[4] SL/TP from entry:')
sl = entry * 1.05
tp = entry * 0.95
print(f'  Entry: {entry}')
print(f'  Stop Loss (price rises 5%): {sl:.2f}')
print(f'  Take Profit (price drops 5%): {tp:.2f}')

print(f'\n[5] Check candles AFTER 9:15:')
after = day[15:]
hit_sl = None
hit_tp = None
for c in after:
    t = c['date'][11:16]
    if c['high'] >= sl:
        hit_sl = t
        break
    if c['low'] <= tp:
        hit_tp = t
        break

if hit_sl:
    print(f'  SL HIT at {hit_sl}! PnL = -5%')
elif hit_tp:
    print(f'  TP HIT at {hit_tp}! PnL = +5%')
else:
    last = day[-1]
    force_pnl = (entry - last['close']) / entry
    print(f'  Neither SL nor TP hit.')
    print(f'  Force close at {last["date"][11:16]}: {last["close"]}')
    print(f'  PnL = ({entry} - {last["close"]}) / {entry} = {force_pnl*100:.2f}%')

print(f'\n[6] Day Summary:')
print(f'  Open: {day[0]["open"]}')
print(f'  High: {max(c["high"] for c in day)}')
print(f'  Low: {min(c["low"] for c in day)}')
print(f'  Close: {day[-1]["close"]}')
print(f'  Total drop from open: {(day[0]["open"] - day[-1]["close"]) / day[0]["open"] * 100:.1f}%')

print(f'\n[7] Comparison:')
print(f'  OLD backtest (entry=open 31.0): PnL = +4.83% (TP hit at 29.45)')
print(f'  FIXED (entry=9:15 price {entry}): see above')
