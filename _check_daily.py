import os, json

base = r'D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線'

# Check daily data structure for a stock that has 1-min data
# Use the index to find a stock
import pickle
with open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_1min_index.pkl', 'rb') as f:
    idx = pickle.load(f)

# Pick stock 2471
stock = '2471'
folder = idx.get(stock)
if folder:
    parent = os.path.dirname(folder)
    print(f"Stock {stock} parent: {parent}")
    print(f"Parent contents: {os.listdir(parent)}")
    
    daily_folder = os.path.join(parent, 'D')
    if os.path.isdir(daily_folder):
        files = sorted(os.listdir(daily_folder))
        print(f"Daily files: {files[:5]}")
        # Read one
        if files:
            fpath = os.path.join(daily_folder, files[0])
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"Keys: {list(data.keys())}")
            bars = data.get('data', [])
            print(f"Bars: {len(bars)}")
            if bars:
                print(f"First: {bars[0]}")
                print(f"Last: {bars[-1]}")
    else:
        print("No D/ folder")
