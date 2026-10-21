import pickle, pandas as pd, numpy as np
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'

sig = pd.read_pickle(f'{OUTPUT_DIR}/gap_fade_signals_2010.pkl')
sig['date'] = pd.to_datetime(sig['date'])

# Get recent signals (2024-2026) to check with yfinance
recent = sig[(sig['date'] >= '2024-01-01')].copy()
recent = recent[(recent['entry'] >= 30) & (recent['entry'] <= 225)]
recent['_abs_gap'] = recent['adj_gap'].abs()
recent = recent[recent['_abs_gap'] >= 0.05]

# Sample 50 stocks
sample = recent.sample(min(50, len(recent)), random_state=42)
print(f'Sampling {len(sample)} signals from 2024-2026')

# Check volume via yfinance
results = []
for _, row in sample.iterrows():
    sid = row['stock']
    date = row['date']
    ticker = f'{sid}.TW'
    try:
        data = yf.download(ticker, start=(date - pd.Timedelta(days=5)).strftime('%Y-%m-%d'), 
                          end=(date + pd.Timedelta(days=1)).strftime('%Y-%m-%d'), progress=False)
        if len(data) >= 2:
            # T-1 volume (day before signal)
            prev_idx = data.index[data.index < date]
            if len(prev_idx) > 0:
                vol_t1 = int(data.loc[prev_idx[-1], ('Volume', '')]) if isinstance(data.columns, pd.MultiIndex) else int(data.loc[prev_idx[-1], 'Volume'])
                dollar_vol = vol_t1 * float(data.loc[prev_idx[-1], ('Close', '')]) if isinstance(data.columns, pd.MultiIndex) else vol_t1 * float(data.loc[prev_idx[-1], 'Close'])
                results.append({'stock': sid, 'date': date, 'vol_t1': vol_t1, 'dollar_vol': dollar_vol, 'gap': row['adj_gap']})
    except:
        pass
    import time
    time.sleep(0.3)

res_df = pd.DataFrame(results)
print(f'\nChecked: {len(res_df)} signals')

if len(res_df) > 0:
    print(f'\n{"=" * 70}')
    print('ACTUAL T-1 VOLUME OF SIGNAL STOCKS')
    print(f'{"=" * 70}')
    print(f'  Volume (shares):')
    print(f'    Min: {res_df["vol_t1"].min():>12,}')
    print(f'    25th: {res_df["vol_t1"].quantile(0.25):>12,.0f}')
    print(f'    Median: {res_df["vol_t1"].median():>12,.0f}')
    print(f'    75th: {res_df["vol_t1"].quantile(0.75):>12,.0f}')
    print(f'    Max: {res_df["vol_t1"].max():>12,}')
    
    print(f'\n  Dollar volume (turnover):')
    print(f'    Min: {res_df["dollar_vol"].min():>15,.0f}')
    print(f'    Median: {res_df["dollar_vol"].median():>15,.0f}')
    print(f'    Max: {res_df["dollar_vol"].max():>15,.0f}')
    
    print(f'\n  Passes 5M share filter: {(res_df["vol_t1"] >= 5_000_000).sum()}/{len(res_df)} ({(res_df["vol_t1"] >= 5_000_000).mean()*100:.0f}%)')
    print(f'  Passes 1M share filter: {(res_df["vol_t1"] >= 1_000_000).sum()}/{len(res_df)} ({(res_df["vol_t1"] >= 1_000_000).mean()*100:.0f}%)')
    print(f'  Passes 500K share filter: {(res_df["vol_t1"] >= 500_000).sum()}/{len(res_df)} ({(res_df["vol_t1"] >= 500_000).mean()*100:.0f}%)')
    
    # Show the low-volume ones
    low_vol = res_df[res_df['vol_t1'] < 1_000_000].sort_values('vol_t1')
    if len(low_vol) > 0:
        print(f'\n  Low volume signals (<1M shares):')
        for _, r in low_vol.iterrows():
            print(f'    {r["stock"]} {r["date"].strftime("%Y-%m-%d")}: vol={r["vol_t1"]:>10,} gap={r["gap"]*100:.1f}%')
