import pickle, os, json

idx = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_1min_index.pkl', 'rb'))

path = idx.get('3296')
print('Path:', path)

if path and os.path.isdir(path):
    files = [f for f in os.listdir(path) if f.endswith('.json')]
    for f in files:
        fpath = os.path.join(path, f)
        with open(fpath, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict) and 'data' in data:
            day = [c for c in data['data'] if c['date'][:10] == '2026-10-02']
            if day:
                day = list(reversed(day))
                print(f'File: {f}, candles for 10/02: {len(day)}')
                print()
                print('=== First 20 min (9:00-9:19) ===')
                for c in day[:20]:
                    t = c['date'][11:16]
                    o, h, l, cl, v = c['open'], c['high'], c['low'], c['close'], c['volume']
                    print(f'  {t} | O={o:.1f} H={h:.1f} L={l:.1f} C={cl:.1f} Vol={v}')
                print()
                print('=== Day summary ===')
                print(f'  Open: {day[0]["open"]}')
                print(f'  High: {max(c["high"] for c in day)}')
                print(f'  Low: {min(c["low"] for c in day)}')
                print(f'  Close: {day[-1]["close"]}')
                print()
                print('=== After 9:15 (entry point) ===')
                for c in day[15:25]:
                    t = c['date'][11:16]
                    o, h, l, cl, v = c['open'], c['high'], c['low'], c['close'], c['volume']
                    print(f'  {t} | O={o:.1f} H={h:.1f} L={l:.1f} C={cl:.1f} Vol={v}')
                break
