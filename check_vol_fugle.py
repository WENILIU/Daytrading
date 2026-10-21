import pickle, pandas as pd, numpy as np, time
from fugle_marketdata import RestClient
import warnings
warnings.filterwarnings('ignore')

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'
API_KEY = 'MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw=='

client = RestClient(api_key=API_KEY)
stock_api = client.stock

sig = pd.read_pickle(f'{OUTPUT_DIR}/gap_fade_signals_2010.pkl')
sig['date'] = pd.to_datetime(sig['date'])

# Get 2026 signals (most recent, stocks still listed)
recent = sig[sig['date'] >= '2026-01-01'].copy()
recent = recent[(recent['entry'] >= 30) & (recent['entry'] <= 225)]
recent['_abs_gap'] = recent['adj_gap'].abs()
recent = recent[recent['_abs_gap'] >= 0.05]

# Sample 30 unique stocks from 2026
sample = recent.drop_duplicates('stock').head(30)
print(f'Checking volume for {len(sample)} stocks from 2026 signals...')

results = []
for i, (_, row) in enumerate(sample.iterrows()):
    sid = row['stock']
    date = row['date']
    try:
        # Get daily candles around signal date
        candles = stock_api.historical.candles(
            symbol=sid, from_=(date - pd.Timedelta(days=5)).strftime('%Y-%m-%d'),
            to=date.strftime('%Y-%m-%d'), timeframe='D', fields='open,high,low,close,volume')
        if candles and 'data' in candles and len(candles['data']) >= 2:
            # T-1 is the second-to-last candle (before signal day)
            data = list(reversed(candles['data']))  # chronological
            # Find the day before signal
            signal_date = date.strftime('%Y-%m-%d')
            prev_days = [c for c in data if c['date'] < signal_date]
            if prev_days:
                prev = prev_days[-1]
                vol_t1 = prev['volume']
                price_t1 = prev['close']
                dollar_vol = vol_t1 * price_t1
                results.append({
                    'stock': sid, 'date': date.strftime('%Y-%m-%d'),
                    'vol_t1': vol_t1, 'price': price_t1,
                    'dollar_vol': dollar_vol, 'gap': row['adj_gap']
                })
    except Exception as e:
        pass
    
    if (i+1) % 10 == 0:
        print(f'  {i+1}/{len(sample)}...')
    time.sleep(1.1)

res_df = pd.DataFrame(results)
print(f'\nChecked: {len(res_df)} stocks')

if len(res_df) > 0:
    print(f'\n{"=" * 70}')
    print('ACTUAL T-1 VOLUME (via Fugle)')
    print(f'{"=" * 70}')
    print(f'  Volume (shares):')
    print(f'    Min:    {res_df["vol_t1"].min():>12,}')
    print(f'    25th:   {res_df["vol_t1"].quantile(0.25):>12,.0f}')
    print(f'    Median: {res_df["vol_t1"].median():>12,.0f}')
    print(f'    75th:   {res_df["vol_t1"].quantile(0.75):>12,.0f}')
    print(f'    Max:    {res_df["vol_t1"].max():>12,}')
    
    print(f'\n  Dollar volume (turnover):')
    print(f'    Min:    {res_df["dollar_vol"].min():>15,.0f}')
    print(f'    Median: {res_df["dollar_vol"].median():>15,.0f}')
    print(f'    Max:    {res_df["dollar_vol"].max():>15,.0f}')
    
    print(f'\n  Passes filters:')
    print(f'    >= 5M shares:  {(res_df["vol_t1"] >= 5_000_000).sum()}/{len(res_df)} ({(res_df["vol_t1"] >= 5_000_000).mean()*100:.0f}%)')
    print(f'    >= 1M shares:  {(res_df["vol_t1"] >= 1_000_000).sum()}/{len(res_df)} ({(res_df["vol_t1"] >= 1_000_000).mean()*100:.0f}%)')
    print(f'    >= 500K shares: {(res_df["vol_t1"] >= 500_000).sum()}/{len(res_df)} ({(res_df["vol_t1"] >= 500_000).mean()*100:.0f}%)')
    print(f'    Turnover >= 10M: {(res_df["dollar_vol"] >= 10_000_000).sum()}/{len(res_df)} ({(res_df["dollar_vol"] >= 10_000_000).mean()*100:.0f}%)')
    
    # Show all
    print(f'\n  All checked stocks:')
    for _, r in res_df.sort_values('vol_t1').iterrows():
        flag = 'OK' if r['vol_t1'] >= 1_000_000 else 'LOW'
        print(f'    {r["stock"]} {r["date"]} gap={r["gap"]*100:+.1f}% vol={r["vol_t1"]:>10,} ({r["dollar_vol"]/1e6:.0f}M) [{flag}]')
