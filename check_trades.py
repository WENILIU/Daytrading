import pickle, pandas as pd
trades = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_v3_trades.pkl', 'rb'))
print(f'Type: {type(trades)}')
if isinstance(trades, pd.DataFrame):
    print(f'Shape: {trades.shape}')
    print(f'Columns: {list(trades.columns)}')
    print(trades.head(3))
    print()
    print(f'Date range: {trades["date"].min()} to {trades["date"].max()}')
    if 'direction' in trades.columns:
        print(f'Directions: {trades["direction"].value_counts().to_dict()}')
    if 'pnl' in trades.columns:
        print(f'WR: {(trades["pnl"]>0).mean()*100:.1f}%')
        print(f'Avg PnL: {trades["pnl"].mean()*100:.3f}%')
    if 'position_pct' in trades.columns:
        print(f'Position: min={trades["position_pct"].min()*100:.1f}% max={trades["position_pct"].max()*100:.1f}%')
    if 'tier' in trades.columns:
        print(f'Tiers: {trades["tier"].value_counts().to_dict()}')
