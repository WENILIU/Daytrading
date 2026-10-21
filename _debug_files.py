import pandas as pd
import pickle
import os

# Load signals
sig_path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl'
signals = pd.read_pickle(sig_path)
signals['date'] = pd.to_datetime(signals['date'])
signals = signals[(signals['date'] >= '2023-05-01') & (signals['date'] <= '2026-01-31')]
signals = signals[signals['direction'] == 'SHORT']

# Load index
with open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_1min_index.pkl', 'rb') as f:
    stock_index = pickle.load(f)

# Check first 10 signals - why do they fail?
print("Checking first 10 signals:")
for i, (idx, sig) in enumerate(signals.head(10).iterrows()):
    stock = str(sig['stock'])
    date_str = sig['date'].strftime('%Y-%m-%d')
    
    folder = stock_index.get(stock)
    if not folder:
        print(f"  {stock} {date_str}: NO FOLDER in index")
        continue
    
    filepath = os.path.join(folder, f"{stock}_{date_str}.json")
    exists = os.path.exists(filepath)
    
    if not exists:
        # Check what files ARE in this folder
        files = os.listdir(folder)
        # Look for files with this date
        matching = [f for f in files if date_str in f]
        print(f"  {stock} {date_str}: FILE NOT FOUND")
        print(f"    Folder: {folder}")
        print(f"    Files with this date: {matching[:3]}")
        if files:
            print(f"    Sample filenames: {files[:3]}")
    else:
        print(f"  {stock} {date_str}: FOUND OK")
