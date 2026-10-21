path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
content = open(path, 'r', encoding='utf-8').read()

# Replace the get_restricted_stocks function with finlab-based version
old_fn_start = 'def get_restricted_stocks() -> set:'
old_fn_end = '    return restricted\n'

start_idx = content.find(old_fn_start)
end_idx = content.find(old_fn_end, start_idx)
if start_idx > 0 and end_idx > 0:
    end_idx += len(old_fn_end)
    new_fn = '''def get_restricted_stocks() -> set:
    """Get today's disposal stocks (cannot do day trading).
    Uses finlab etl:disposal_stock_filter if available, else exchange API."""
    restricted = set()
    
    # Method 1: finlab (most reliable)
    try:
        from finlab import data as fdata
        from datetime import date
        today = date.today().strftime('%Y%m%d')
        disposal_df = fdata.get('etl:disposal_stock_filter', as_of=today)
        if disposal_df is not None and len(disposal_df) > 0:
            # Get the latest date row
            latest_date = disposal_df.index[-1]
            row = disposal_df.loc[latest_date]
            # False = IS disposal (cannot trade)
            disposal_stocks = row[~row].index.tolist()
            restricted.update(disposal_stocks)
    except Exception:
        pass
    
    # Method 2: Exchange API fallback
    if not restricted:
        try:
            import requests
            url = "https://www.twse.com.tw/zh/api/tradingReference/stockRestriction"
            resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code == 200:
                data = resp.json()
                for row in data.get('data', []):
                    if len(row) >= 2:
                        restricted.add(str(row[1]).strip())
        except Exception:
            pass
    
    # Always exclude known non-day-trade stocks
    restricted.update(['2330', '2317'])
    
    return restricted
'''
    content = content[:start_idx] + new_fn + content[end_idx:]
    open(path, 'w', encoding='utf-8').write(content)
    print("Updated get_restricted_stocks() with finlab support")
else:
    print(f"Function not found: start={start_idx}, end={end_idx}")
