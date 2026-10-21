import pandas as pd
sigs = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")
sigs['date_dt'] = pd.to_datetime(sigs['date'])
print(f"Signals range: {sigs['date_dt'].min()} to {sigs['date_dt'].max()}")
print(f"Total: {len(sigs)}")
latest = sigs[sigs['date_dt'] >= '2026-09-01']
print(f"After 2026-09: {len(latest)}")
if len(latest) > 0:
    print(f"Latest: {latest['date_dt'].max()}")
    # Show last few dates
    dates = sorted(latest['date'].unique())
    print(f"Dates: {dates[-10:]}")
