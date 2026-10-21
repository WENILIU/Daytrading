import json, os

base = r'D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線'
target = os.path.join(base, 'A2330', '1')

if os.path.isdir(target):
    files = sorted(os.listdir(target))
    print(f"A2330 1-min files: {len(files)}")
    for fname in files[-10:]:
        fpath = os.path.join(target, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if len(data['data']) > 0:
            print(f"\n{fname}: {len(data['data'])} bars")
            print("First:", data['data'][0])
            print("Last:", data['data'][-1])
            break
else:
    print("A2330 not found, trying others...")
    for d in sorted(os.listdir(base)):
        p = os.path.join(base, d, '1')
        if not os.path.isdir(p):
            continue
        for fname in sorted(os.listdir(p)):
            fpath = os.path.join(p, fname)
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if len(data['data']) > 10:
                print(f"{d}/{fname}: {len(data['data'])} bars")
                print("First:", data['data'][0])
                print("Last:", data['data'][-1])
                break
        break
