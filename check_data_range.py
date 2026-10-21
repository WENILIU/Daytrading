import pickle, os, pandas as pd
idx = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_1min_index.pkl', 'rb'))
strat = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
strat['date'] = pd.to_datetime(strat['date'])
print(f"Backtest data: {strat['date'].min().date()} to {strat['date'].max().date()}")
print(f"Signals: {len(strat)}")

# Check actual file coverage
top_stocks = strat['stock'].value_counts().head(5).index.tolist()
for stock in top_stocks:
    if stock in idx:
        path = idx[stock]
        if os.path.isdir(path):
            files = [f.replace('.json','').split('_',1)[1] for f in os.listdir(path) if f.endswith('.json')]
            dates = sorted(files)
            if dates:
                print(f"  {stock}: {dates[0]} to {dates[-1]} ({len(dates)} days)")

# Check overall date distribution
print(f"\nSignals by month:")
monthly = strat.groupby(strat['date'].dt.to_period('M')).size()
for period, count in monthly.items():
    print(f"  {period}: {count}")
