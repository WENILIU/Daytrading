import time, os, json, pickle
import pandas as pd
import numpy as np
from datetime import datetime
from fugle_marketdata import RestClient
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

API_KEY = 'MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw=='
OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'
DATA_ROOT = r'D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線'

client = RestClient(api_key=API_KEY)
stock = client.stock

print('=' * 60)
print('EXTEND BACKTEST: 2026-07 to 2026-10 (fast mode)')
print('=' * 60)

# Step 1: Get stock list from Fugle (1 call)
print()
print('[1/5] Getting stock list...')
twse = stock.intraday.tickers(type='EQUITY', exchange='TWSE', isNormal=True)
tpex = stock.intraday.tickers(type='EQUITY', exchange='TPEx', isNormal=True)

all_stocks = []
for d in twse['data']:
    sid = d['symbol']
    if 'A' in sid or len(sid) > 4:
        continue
    all_stocks.append(sid)
for d in tpex['data']:
    sid = d['symbol']
    if 'A' in sid or len(sid) > 4:
        continue
    all_stocks.append(sid)

print(f'  Total stocks: {len(all_stocks)}')

# Step 2: Download daily data via yfinance (batch, fast)
print()
print('[2/5] Downloading daily data via yfinance...')

tickers = [f'{sid}.TW' for sid in all_stocks]

# Download in batches of 200 to avoid timeout
all_daily = []
batch_size = 200
for i in range(0, len(tickers), batch_size):
    batch = tickers[i:i+batch_size]
    try:
        data = yf.download(batch, start='2026-06-10', end='2026-10-20', group_by='ticker', progress=False)
        if data is not None and len(data) > 0:
            for ticker in batch:
                sid = ticker.replace('.TW', '')
                if ticker in data.columns.get_level_values(0):
                    tdata = data[ticker].dropna(subset=['Open', 'Close'])
                    for date, row in tdata.iterrows():
                        all_daily.append({
                            'date': date,
                            'stock': sid,
                            'open': float(row['Open']),
                            'high': float(row['High']),
                            'low': float(row['Low']),
                            'close': float(row['Close']),
                            'volume': int(row['Volume'])
                        })
    except Exception as e:
        print(f'  Batch {i//batch_size} error: {e}')
    
    print(f'  Batch {i//batch_size + 1}/{(len(tickers)-1)//batch_size + 1} done, total rows: {len(all_daily)}')
    time.sleep(1)

df = pd.DataFrame(all_daily)
df['date'] = pd.to_datetime(df['date'])
print(f'  Total daily records: {len(df)}')
print(f'  Date range: {df["date"].min().date()} to {df["date"].max().date()}')
print(f'  Unique stocks: {df["stock"].nunique()}')

# Step 3: Compute gap signals
print()
print('[3/5] Computing gap signals...')

df = df.sort_values(['stock', 'date']).reset_index(drop=True)
df['prev_close'] = df.groupby('stock')['close'].shift(1)
df['raw_gap'] = (df['open'] - df['prev_close']) / df['prev_close']
df['day_change'] = df.groupby('stock')['close'].pct_change()

market_ret = df.groupby('date')['day_change'].mean().rename('market_ret')
df = df.merge(market_ret.reset_index(), on='date')
df['adj_gap'] = df['raw_gap'] - df['market_ret']

# Only new data
df = df[df['date'] >= '2026-06-19']

signals = df[df['adj_gap'].abs() >= 0.05].copy()
signals['direction'] = np.where(signals['adj_gap'] > 0, 'SHORT', 'LONG')
signals = signals[(signals['open'] >= 30) & (signals['open'] <= 225)]

n_short = (signals['direction']=='SHORT').sum()
n_long = (signals['direction']=='LONG').sum()
print(f'  Gap signals: {len(signals)}')
print(f'  SHORT: {n_short}, LONG: {n_long}')
print(f'  Unique stocks: {signals["stock"].nunique()}')
print(f'  Date range: {signals["date"].min().date()} to {signals["date"].max().date()}')

sig_daily = signals[['date', 'stock', 'direction', 'raw_gap', 'adj_gap', 'market_ret', 'open', 'high', 'low', 'close']].copy()
sig_daily = sig_daily.rename(columns={'open': 'entry'})
pickle.dump(sig_daily, open(os.path.join(OUTPUT_DIR, 'gap_signals_2026H2.pkl'), 'wb'))

# Step 4: Load 1-min data (local first, Fugle for missing)
print()
print('[4/5] Loading 1-min data...')

short_signals = signals[signals['direction'] == 'SHORT'].copy()
signal_stocks = short_signals['stock'].unique().tolist()
print(f'  Need 1-min for {len(signal_stocks)} stocks')

# Load stock_1min_index for local data
idx = pickle.load(open(os.path.join(OUTPUT_DIR, 'stock_1min_index.pkl'), 'rb'))

min1_data = {}
need_download = []

for sid in signal_stocks:
    if sid in idx:
        path = idx[sid]
        if os.path.isdir(path):
            # Find files that might contain 2026-07+ data
            files = [f for f in os.listdir(path) if f.endswith('.json')]
            for f in files:
                fpath = os.path.join(path, f)
                try:
                    with open(fpath, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                    if isinstance(data, dict) and 'data' in data:
                        # Check if this file has 2026-07+ data
                        has_new = any(d['date'][:7] >= '2026-07' for d in data['data'][:10])
                        if has_new:
                            # Reverse to chronological order
                            min1_data[sid] = list(reversed(data['data']))
                            break
                except:
                    pass
            if sid not in min1_data:
                need_download.append(sid)
        else:
            need_download.append(sid)
    else:
        need_download.append(sid)

print(f'  Found locally: {len(min1_data)} stocks')
print(f'  Need to download: {len(need_download)} stocks')

# Download missing from Fugle
if need_download:
    print(f'  Downloading {len(need_download)} from Fugle...')
    batch_start = time.time()
    count = 0
    for i, sid in enumerate(need_download):
        try:
            candles = stock.historical.candles(symbol=sid, from_='2026-06-19', to='2026-10-19',
                timeframe='1', fields='open,high,low,close,volume')
            if candles and 'data' in candles and len(candles['data']) > 0:
                min1_data[sid] = list(reversed(candles['data']))
        except:
            pass
        count += 1
        if count >= 60:
            elapsed = time.time() - batch_start
            wait = max(0, 65 - elapsed) + 2
            time.sleep(wait)
            batch_start = time.time()
            count = 0
        if (i + 1) % 20 == 0:
            print(f'    Progress: {i+1}/{len(need_download)}, got {len(min1_data)}')
    print(f'  Total 1-min data: {len(min1_data)} stocks')

# Step 5: Confirmation + PnL
print()
print('[5/5] Applying confirmation + computing PnL...')

results = []
for _, sig in short_signals.iterrows():
    sid = sig['stock']
    date = sig['date']
    entry = sig['open']

    if sid not in min1_data:
        continue

    date_str = date.strftime('%Y-%m-%d')
    day_candles = [c for c in min1_data[sid] if c['date'][:10] == date_str]
    if len(day_candles) < 16:
        continue

    first_15 = day_candles[:15]
    open_price = first_15[0]['open']
    min_price_15 = min(c['low'] for c in first_15)
    early_move = (open_price - min_price_15) / open_price

    if early_move < 0.025:
        continue

    sl_price = entry * 1.05
    tp_price = entry * 0.95

    pnl = None
    exit_reason = None

    for c in day_candles:
        if c['high'] >= sl_price:
            pnl = -0.05
            exit_reason = 'SL'
            break
        if c['low'] <= tp_price:
            pnl = 0.05
            exit_reason = 'TP'
            break

    if pnl is None:
        last_close = day_candles[-1]['close']
        pnl = (entry - last_close) / entry
        exit_reason = 'FORCE'

    pnl -= 0.0017

    results.append({
        'date': date,
        'stock': sid,
        'direction': 'SHORT',
        'pnl': pnl,
        'early_move_15': -early_move,
        'entry': entry,
        'adj_gap': sig['adj_gap'],
        'exit_reason': exit_reason
    })

results_df = pd.DataFrame(results)
print()
print(f'  Confirmed trades: {len(results_df)}')
if len(results_df) > 0:
    wr = (results_df['pnl']>0).mean()*100
    avg_pnl = results_df['pnl'].mean()*100
    rmin = results_df['date'].min().date()
    rmax = results_df['date'].max().date()
    print(f'  Win rate: {wr:.1f}%')
    print(f'  Avg PnL: {avg_pnl:.2f}%')
    print(f'  Date range: {rmin} to {rmax}')

    pickle.dump(results_df, open(os.path.join(OUTPUT_DIR, 'full_1min_results_2026H2.pkl'), 'wb'))
    print('  Saved full_1min_results_2026H2.pkl')

print()
print('=' * 60)
print('DONE')
print('=' * 60)
