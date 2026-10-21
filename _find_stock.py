import os

base = r'D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線'
items = sorted(os.listdir(base))

# Look for 2330, 2539, or similar
targets = ['2330', '2539', 'A2330', 'A2539']
for t in targets:
    if t in items:
        print(f"Found: {t}")
        p = os.path.join(base, t, '1')
        if os.path.isdir(p):
            files = sorted(os.listdir(p))
            print(f"  1-min files: {len(files)}, first: {files[0] if files else 'none'}")
    else:
        print(f"Not found: {t}")

# Check naming pattern
print(f"\nAll folder prefixes:")
prefixes = set()
for item in items:
    if item[0].isalpha():
        prefixes.add(item[0])
    else:
        prefixes.add('NUMERIC')
print(f"  Prefixes: {prefixes}")

# Check if there are numeric folders
numeric = [x for x in items if x[0].isdigit()]
print(f"  Numeric folders: {len(numeric)}, first 5: {numeric[:5]}")
