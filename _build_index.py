import os, json
from pathlib import Path

base = Path(r'D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線')

# Build index: stock_code -> folder path
# Files are named like: {stock_code}_{date}.json
index = {}
count = 0

for folder in base.iterdir():
    if not folder.is_dir():
        continue
    one_min = folder / '1'
    if not one_min.is_dir():
        continue
    # Get stock code from first file
    files = list(one_min.iterdir())
    if not files:
        continue
    # Extract stock code from filename
    fname = files[0].stem  # e.g. "6741_2025-03-26"
    code = fname.split('_')[0]
    if code not in index:
        index[code] = str(one_min)
    count += 1
    if count % 500 == 0:
        print(f"  Scanned {count} folders, indexed {len(index)} codes...")

print(f"\nDone. Indexed {len(index)} stock codes from {count} folders.")

# Save index
import pickle
with open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_1min_index.pkl', 'wb') as f:
    pickle.dump(index, f)
print("Index saved.")

# Verify some codes
test_codes = ['2330', '2539', '8938', '2454', '6741']
for c in test_codes:
    if c in index:
        print(f"  {c}: FOUND")
    else:
        print(f"  {c}: not found")
