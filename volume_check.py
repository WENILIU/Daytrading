import pickle, os, json
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'

# Load signals
sig = pd.read_pickle(f'{OUTPUT_DIR}/gap_fade_signals_2010.pkl')
sig['date'] = pd.to_datetime(sig['date'])

# Get signals that pass basic filters
short = sig[sig['direction'] == 'SHORT'].copy()
short = short[short['adj_gap'] >= 0.05]
short = short[(short['entry'] >= 30) & (short['entry'] <= 225)]

long = sig[sig['direction'] == 'LONG'].copy()
long = long[long['adj_gap'] <= -0.05]
long = long[(long['entry'] >= 30) & (long['entry'] <= 225)]

all_sig = pd.concat([short, long], ignore_index=True)
print(f'Signals before volume filter: {len(all_sig)}')

# Load 1-min index to estimate volume
idx = pickle.load(open(f'{OUTPUT_DIR}/stock_1min_index.pkl', 'rb'))

# Sample: check volume for a subset of signals
# Group by stock, load data, compute daily volume
stock_groups = all_sig.groupby('stock')
volume_data = []
processed = 0

for sid, group in stock_groups:
    if sid not in idx:
        continue
    path = idx[sid]
    if not os.path.isdir(path):
        continue
    
    # Load all files for this stock
    day_volumes = {}
    files = [f for f in os.listdir(path) if f.endswith('.json')]
    for f in files:
        fpath = os.path.join(path, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if isinstance(data, dict) and 'data' in data:
                for c in data['data']:
                    d = c['date'][:10]
                    if d not in day_volumes:
                        day_volumes[d] = 0
                    day_volumes[d] += c['volume']
        except:
            pass
        del data
    
    # Match with signals
    for _, row in group.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        # Use previous day volume as proxy (T-1 volume, same as live script)
        # Find the day before
        prev_dates = [d for d in day_volumes if d < date_str]
        if prev_dates:
            prev_day = max(prev_dates)
            vol_t1 = day_volumes[prev_day]
        else:
            vol_t1 = day_volumes.get(date_str, 0)
        
        volume_data.append({
            'date': row['date'],
            'stock': sid,
            'vol_t1': vol_t1,
            'direction': row['direction'],
            'adj_gap': row['adj_gap'],
            'entry': row['entry']
        })
    
    processed += 1
    if processed % 200 == 0:
        print(f'  {processed}/{len(stock_groups)}...')

vol_df = pd.DataFrame(volume_data)
print(f'\nVolume data available: {len(vol_df)} signals')

# Volume distribution
print(f'\n{"=" * 70}')
print('VOLUME DISTRIBUTION (T-1 daily volume, shares)')
print(f'{"=" * 70}')
for threshold in [0, 500_000, 1_000_000, 2_000_000, 5_000_000, 10_000_000, 20_000_000]:
    count = (vol_df['vol_t1'] >= threshold).sum()
    pct = count / len(vol_df) * 100
    print(f'  Volume >= {threshold:>12,}: {count:>6} signals ({pct:.1f}%)')

# Dollar volume (more meaningful)
vol_df['dollar_vol'] = vol_df['vol_t1'] * vol_df['entry']
print(f'\n  Dollar volume (T-1 turnover):')
for threshold in [0, 10_000_000, 50_000_000, 100_000_000, 500_000_000]:
    count = (vol_df['dollar_vol'] >= threshold).sum()
    pct = count / len(vol_df) * 100
    label = f'{threshold/1e6:.0f}M' if threshold >= 1e6 else f'{threshold:,}'
    print(f'  Turnover >= {label:>10}: {count:>6} signals ({pct:.1f}%)')

# Impact on backtest
print(f'\n{"=" * 70}')
print('IMPACT ON BACKTEST (volume filter)')
print(f'{"=" * 70}')

# Merge volume into full backtest
all_sig_with_vol = all_sig.merge(vol_df[['date', 'stock', 'vol_t1']], on=['date', 'stock'], how='left')
has_vol = all_sig_with_vol['vol_t1'].notna()
print(f'  Signals with volume data: {has_vol.sum()} / {len(all_sig_with_vol)}')

# Run backtest with different volume thresholds
CAPITAL = 4_500_000
SL_PCT = 0.06
TP_PCT = 0.04
COST = 0.0017
BASE_POS = 0.05
HIGH_MULT = 1.5
MAX_POS = 15
MAX_EXP = 0.70

def run_backtest(subset):
    subset = subset.copy()
    subset['_abs_gap'] = subset['adj_gap'].abs()
    subset['pos_pct'] = np.where(subset['_abs_gap'] > 0.07, BASE_POS * HIGH_MULT, BASE_POS)
    
    # PnL
    is_short = subset['direction'] == 'SHORT'
    sl_hit = np.where(is_short, subset['day_high'] >= subset['entry'] * (1 + SL_PCT), subset['day_low'] <= subset['entry'] * (1 - SL_PCT))
    tp_hit = np.where(is_short, subset['day_low'] <= subset['entry'] * (1 - TP_PCT), subset['day_high'] >= subset['entry'] * (1 + TP_PCT))
    force_pnl = np.where(is_short, (subset['entry'] - subset['day_close']) / subset['entry'], (subset['day_close'] - subset['entry']) / subset['entry'])
    subset['pnl'] = np.where(tp_hit, TP_PCT, np.where(sl_hit, -SL_PCT, force_pnl)) - COST
    
    subset['shares'] = np.floor(subset['pos_pct'] * CAPITAL / subset['entry'] / 1000).astype(int) * 1000
    subset = subset[subset['shares'] >= 1000]
    subset['actual_pos'] = (subset['shares'] * subset['entry']) / CAPITAL
    
    subset = subset.sort_values(['date', '_abs_gap'], ascending=[True, False])
    subset['day_rank'] = subset.groupby('date').cumcount()
    subset = subset[subset['day_rank'] < MAX_POS]
    subset['cum_exp'] = subset.groupby('date')['actual_pos'].cumsum()
    subset = subset[subset['cum_exp'] <= MAX_EXP]
    
    subset['dollar_pnl'] = subset['pnl'] * subset['actual_pos'] * CAPITAL
    daily_pnl = subset.groupby('date')['dollar_pnl'].sum()
    daily_ret = daily_pnl / CAPITAL
    cum = (1 + daily_ret).cumprod()
    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
    cagr = cum.iloc[-1] ** (1/years) - 1
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
    return len(subset), cagr, mdd, sharpe

# Test different volume thresholds
for vol_min in [0, 1_000_000, 2_000_000, 5_000_000, 10_000_000]:
    # Only test on signals that have volume data
    test = all_sig_with_vol[all_sig_with_vol['vol_t1'].notna()].copy()
    if vol_min > 0:
        test = test[test['vol_t1'] >= vol_min]
    
    n, cagr, mdd, sharpe = run_backtest(test)
    print(f'  Vol>={vol_min:>10,}: {n:>6} trades | CAGR={cagr*100:.0f}% | MDD={mdd*100:.1f}% | Sharpe={sharpe:.1f}')
