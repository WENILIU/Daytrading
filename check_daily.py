import os, json, glob

# Check daily K data range
base = r'D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線'
# Find a sample stock's daily data
stocks = os.listdir(base)[:5]
for stock in stocks:
    daily_path = os.path.join(base, stock, 'D')
    if os.path.isdir(daily_path):
        files = sorted(os.listdir(daily_path))
        if files:
            # Read last file to check date range
            last_file = os.path.join(daily_path, files[-1])
            try:
                data = json.load(open(last_file, 'r', encoding='utf-8'))
                if isinstance(data, list) and len(data) > 0:
                    dates = [d.get('timestamp','')[:10] for d in data if 'timestamp' in d]
                    if dates:
                        print(f"{stock}: {files[-1]} -> dates {min(dates)} to {max(dates)} ({len(dates)} days)")
            except:
                print(f"{stock}: {files[-1]} (parse error)")
        break

# Also check the 1-min data structure
print("\n=== 1-min data structure ===")
for stock in stocks[:3]:
    min1_path = os.path.join(base, stock, '1')
    if os.path.isdir(min1_path):
        files = sorted(os.listdir(min1_path))
        print(f"{stock}/1/: {len(files)} files, last: {files[-1] if files else 'none'}")
