import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

# Load daily signals to check previous-day conditions
signals = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl', 'rb'))
signals['date'] = pd.to_datetime(signals['date'])

# 處置股 criteria (TWSE rules):
# A stock becomes 處置 if on the PREVIOUS trading day:
#   - Price change >= 3.5% (up or down), OR
#   - Volume increased >= 35% vs average
#   - OR other abnormal conditions
#
# Our signals have: entry (today's open), day_high, day_low, day_close
# We need PREVIOUS day close to check if yesterday's move was abnormal
# 
# The signal data has 'raw_gap' = (today_open - prev_close) / prev_close
# And we can reconstruct: prev_close = entry / (1 + raw_gap)
# But we don't have the day BEFORE that (T-2 close) to check T-1's move.
#
# Alternative: check if the same stock appeared in signals on consecutive days
# If stock X had a signal yesterday AND today, today it's likely 處置

# Load 1-min data for our strategy signals
data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

# Our strategy signals
subset = data[(data['direction']=='SHORT') & (data['fav_move'] >= 0.025) & 
              (data['entry'] >= 30) & (data['entry'] <= 225)].copy()
subset = subset.sort_values(['stock', 'date'])

# Check: same stock appearing on consecutive days
subset['prev_date'] = subset.groupby('stock')['date'].shift(1)
subset['days_since_prev'] = (subset['date'] - subset['prev_date']).dt.days

# If same stock had a signal 1-2 days ago, it's likely 處置 today
consecutive = subset[subset['days_since_prev'] <= 2]
print(f"Total signals: {len(subset)}")
print(f"Same stock within 2 days (likely 處置): {len(consecutive)} ({len(consecutive)/len(subset)*100:.1f}%)")

# More precise: check if the stock had a LARGE GAP the day before
# A stock that gapped up >5% yesterday would be 處置 today
# We can check: for each signal, did the same stock have a signal 1 day before?
one_day = subset[subset['days_since_prev'] == 1]
print(f"Same stock exactly 1 day before: {len(one_day)} ({len(one_day)/len(subset)*100:.1f}%)")

# Even broader: check the full daily signals for previous-day activity
# If a stock had ANY signal (gap >5%) yesterday, it's 處置 today
all_signals = signals.copy()
all_signals['prev_signal'] = False
for stock, group in all_signals.groupby('stock'):
    dates = set(group['date'])
    for idx, row in group.iterrows():
        prev_day = row['date'] - pd.Timedelta(days=1)
        # Check weekday
        while prev_day.weekday() >= 5:
            prev_day -= pd.Timedelta(days=1)
        if prev_day in dates:
            all_signals.loc[idx, 'prev_signal'] = True

# Apply to our strategy signals
our_stocks = set(subset['stock'])
our_dates = set(zip(subset['date'], subset['stock']))
affected = 0
for _, row in subset.iterrows():
    key = (row['date'], row['stock'])
    # Check if this stock had a signal the day before
    prev_day = row['date'] - pd.Timedelta(days=1)
    while prev_day.weekday() >= 5:
        prev_day -= pd.Timedelta(days=1)
    prev_key = (prev_day, row['stock'])
    prev_signals = all_signals[(all_signals['date'] == prev_day) & (all_signals['stock'] == row['stock'])]
    if len(prev_signals) > 0:
        affected += 1

print(f"\nSignals where stock had signal YESTERDAY (likely 處置): {affected} ({affected/len(subset)*100:.1f}%)")

# Now simulate WITHOUT these
# Rebuild without consecutive-day signals
clean = subset.copy()
clean['prev_date'] = clean.groupby('stock')['date'].shift(1)
clean['days_since_prev'] = (clean['date'] - clean['prev_date']).dt.days
clean = clean[clean['days_since_prev'].isna() | (clean['days_since_prev'] > 2)]

print(f"\nSignals after removing 處置 risk: {len(clean)} (removed {len(subset)-len(clean)})")

# Simulate with clean data
tiers = [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)]
capital = 4_500_000

def run_sim(trade_data):
    mult = np.zeros(len(trade_data))
    for min_move, m in sorted(tiers, reverse=True):
        cond = (trade_data['fav_move'].values >= min_move) & (mult == 0)
        mult[cond] = m
    trade_data = trade_data.copy()
    trade_data['multiplier'] = mult
    trade_data = trade_data[trade_data['multiplier'] > 0]
    if len(trade_data) == 0: return None
    trade_data['pos_pct'] = 0.08 * trade_data['multiplier']
    trade_data['shares'] = np.floor(trade_data['pos_pct'] * capital / trade_data['entry'] / 1000).astype(int) * 1000
    trade_data = trade_data[trade_data['shares'] >= 1000]
    trade_data['actual_pos_pct'] = (trade_data['shares'] * trade_data['entry']) / capital
    trade_data = trade_data.sort_values(['date', 'fav_move'], ascending=[True, False])
    trade_data['day_rank'] = trade_data.groupby('date').cumcount()
    trade_data = trade_data[trade_data['day_rank'] < 10]
    trade_data['cum_exp'] = trade_data.groupby('date')['actual_pos_pct'].cumsum()
    trade_data = trade_data[trade_data['cum_exp'] <= 0.50]
    if len(trade_data) == 0: return None
    trade_data['dollar_pnl'] = trade_data['pnl'] * trade_data['actual_pos_pct'] * capital
    daily_pnl = trade_data.groupby('date')['dollar_pnl'].sum()
    daily_ret = daily_pnl / capital
    cum = (1 + daily_ret).cumprod()
    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
    cagr = cum.iloc[-1] ** (1/years) - 1
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
    return {'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe, 'trades': len(trade_data),
            'win_rate': (trade_data['pnl'] > 0).mean(), 'daily_avg': daily_pnl.mean()}

print("\n=== WITH 處置 stocks (current) ===")
r1 = run_sim(subset)
if r1:
    print(f"  WR={r1['win_rate']*100:.1f}% CAGR={r1['cagr']*100:.0f}% MDD={r1['mdd']*100:.1f}% trades={r1['trades']}")

print("\n=== WITHOUT 處置 stocks (filtered) ===")
r2 = run_sim(clean)
if r2:
    print(f"  WR={r2['win_rate']*100:.1f}% CAGR={r2['cagr']*100:.0f}% MDD={r2['mdd']*100:.1f}% trades={r2['trades']}")
