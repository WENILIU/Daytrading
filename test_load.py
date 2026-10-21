import pandas as pd, numpy as np, json, time
from pathlib import Path

# Rebuild index properly - map stock code to folder
DATA_DIR = Path(r"D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線")
INDEX_FILE = Path(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_path_index.json")

# Verify index works
with open(INDEX_FILE, "r", encoding="utf-8") as f:
    INDEX = json.load(f)

# Test: can we find 2395_2023-05.json?
folder = INDEX.get("2395", "")
print(f"2395 folder: {folder}")
if folder:
    fp = Path(folder) / "2395_2023-05.json"
    print(f"File exists: {fp.exists()}")
    if fp.exists():
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"Type: {type(data)}, keys: {list(data.keys()) if isinstance(data,dict) else 'list'}")
        if isinstance(data, dict) and "data" in data:
            bars = data["data"]
            print(f"Bars: {len(bars)}")
            print(f"First bar: {bars[0]}")
            # Check date range
            dates = sorted(set(b["date"][:10] for b in bars))
            print(f"Date range: {dates[0]} to {dates[-1]}, {len(dates)} days")
