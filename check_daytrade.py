import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

# Filter to our strategy signals (SHORT, confirm>=2.5%)
subset = data[(data['direction']=='SHORT') & (data['fav_move'] >= 0.025)].copy()
print(f"Strategy signals: {len(subset)}")

# Known stocks that DON'T support 現股當沖:
# 2330 (台積電), 2317 (鴻海) are confirmed from our testing
# The full list is published by TWSE/TPEx. Common exclusions include:
# - Stocks with very high price (>5000 typically excluded by our filter already)
# - Specific stocks designated by exchange
# Let me check which stocks appear in our signals
stock_counts = subset['stock'].value_counts()
print(f"\nUnique stocks in signals: {len(stock_counts)}")
print(f"\nTop 20 stocks by signal count:")
for stock, count in stock_counts.head(20).items():
    print(f"  {stock}: {count} signals")

# Check for known non-當沖 stocks
known_no_dt = ['2330', '2317']  # Confirmed from testing
affected = subset[subset['stock'].isin(known_no_dt)]
print(f"\n\nKnown non-當沖 stocks in signals: {len(affected)}")
if len(affected) > 0:
    print(affected[['date', 'stock', 'entry', 'pnl']].to_string())

# Check high-price stocks (likely can't do 當沖 or already filtered)
high_price = subset[subset['entry'] > 500]
print(f"\nSignals with price > 500: {len(high_price)}")
high_price2 = subset[subset['entry'] > 1000]
print(f"Signals with price > 1000: {len(high_price2)}")

# The real question: which stocks are on the exchange's non-當沖 list?
# TWSE publishes this. Let me check via the stock list
# Common non-當沖: 2330, 2317, and some ETFs/特殊股
# Let me try to get the list from Fugle or check patterns
print("\n\n=== Checking if any signal stocks are likely non-當沖 ===")
# Stocks that are typically excluded from 當沖:
# - 2330 台積電 (confirmed)
# - 2317 鴻海 (confirmed)  
# - Some high-price stocks
# - Stocks under special monitoring
# Let me see if our price filter (max 225) already excludes most problematic ones
print(f"Price range in signals: {subset['entry'].min():.0f} - {subset['entry'].max():.0f}")
print(f"Signals with price > 225 (our filter): {len(subset[subset['entry'] > 225])}")

# Actually our live scanner already filters max_price=225
# But the backtest data might include higher prices
over_225 = subset[subset['entry'] > 225]
print(f"\nBacktest signals above 225 (would be filtered in live): {len(over_225)}")
if len(over_225) > 0:
    print(f"  Their WR: {(over_225['pnl']>0).mean()*100:.1f}%")
    print(f"  Their avg PnL: {over_225['pnl'].mean()*100:.2f}%")
