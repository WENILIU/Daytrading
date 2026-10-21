import os, json, time
from pathlib import Path

DATA_DIR = Path(r"D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線")
INDEX_FILE = Path(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_path_index.json")

if INDEX_FILE.exists():
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        index = json.load(f)
    print(f"Loaded index: {len(index)} stocks")
else:
    print("Building index (scanning all folders)...")
    t0 = time.time()
    index = {}
    
    for company_dir in DATA_DIR.iterdir():
        if not company_dir.is_dir():
            continue
        freq_dir = company_dir / "1"
        if not freq_dir.exists():
            continue
        for json_file in freq_dir.glob("*.json"):
            # filename: {code}_{year-month}.json
            stem = json_file.stem
            parts = stem.split("_")
            if len(parts) >= 2:
                code = parts[0]
                if code not in index:
                    index[code] = str(freq_dir)
    
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    
    print(f"Built index: {len(index)} stocks in {time.time()-t0:.1f}s")
