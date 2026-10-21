import pandas as pd
import numpy as np
import pickle
import os
import glob
from pathlib import Path
from datetime import datetime

# Load signals
sig_path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl'
signals = pd.read_pickle(sig_path)

# Filter to period with 1-min data (2023-05 onwards)
signals['date'] = pd.to_datetime(signals['date'])
signals = signals[signals['date'] >= '2023-05-01']
signals = signals[signals['date'] <= '2026-01-31']

print(f"Signals in 1-min data range: {len(signals)}")
print(f"Date range: {signals['date'].min()} to {signals['date'].max()}")

# 1-min data path
data_root = r'D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線'

# Config
SL = 0.06
TP = 0.04
COST = 0.0023
FORCE_CLOSE_TIME = '13:25'

# Test each confirmation minute from 9:01 to 9:30
confirm_minutes = list(range(1, 31))  # 9:01 to 9:30

results = {m: [] for m in confirm_minutes}

# Process signals by stock to minimize file reads
stock_groups = signals.groupby('symbol')
total_stocks = len(stock_groups)
print(f"Processing {total_stocks} stocks...")

processed = 0

for symbol, group in stock_groups:
    processed += 1
    if processed % 200 == 0:
        print(f"  Progress: {processed}/{total_stocks} stocks")
    
    # Find 1-min data file
    # Format: {symbol}_1min_{year}.csv or similar
    # Let me check the actual file structure
    pass

# First, let me check the file structure
sample_dir = os.path.join(data_root, '')
dirs = os.listdir(data_root)[:5]
print(f"\nData root contents (first 5): {dirs}")
