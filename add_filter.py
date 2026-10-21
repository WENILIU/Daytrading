path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
content = open(path, 'r', encoding='utf-8').read()

# Add a function to download 處置股 list from TWSE/TPEx
# Insert after the imports section, before the Config class
filter_code = '''
def get_restricted_stocks() -> set:
    """Download today's restricted stocks (處置股/停止買賣) from TWSE/TPEx.
    These stocks cannot do day trading (現股當沖)."""
    import requests
    restricted = set()
    
    # TWSE 處置股 (stockRestriction)
    try:
        url = "https://www.twse.com.tw/zh/api/tradingReference/stockRestriction"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for row in data.get('data', []):
                # Format: [date, stock_code, stock_name, restriction_type, ...]
                if len(row) >= 2:
                    restricted.add(str(row[1]).strip())
    except Exception:
        pass
    
    # TPEx 處置股
    try:
        url = "https://www.tpex.org.tw/web/stock/aftertrading/stocksuspension/stk_suspension.php?l=zh-tw&o=json&s=0,asc,0"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for row in data.get('data', []):
                if len(row) >= 1:
                    restricted.add(str(row[0]).strip())
    except Exception:
        pass
    
    # Also add known non-day-trade stocks
    restricted.update(['2330', '2317'])
    
    return restricted

'''

# Insert before "class Config:"
insert_point = content.find('class Config:')
if insert_point > 0:
    content = content[:insert_point] + filter_code + content[insert_point:]
    print("Added get_restricted_stocks() function")

# Now add the filter to scan_signals - after the gap detection, before adding to candidates
old_scan = '''                if direction is None:
                    continue

                candidates.append(Signal('''

new_scan = '''                if direction is None:
                    continue

                # Skip 處置股 (cannot do day trading)
                if result["symbol"] in self.restricted_stocks:
                    continue

                candidates.append(Signal('''

if old_scan in content:
    content = content.replace(old_scan, new_scan)
    print("Added 處置股 filter to scan_signals")
else:
    print("Scan pattern not found, checking...")
    idx = content.find("if direction is None:")
    print(f"Found at {idx}")

# Initialize restricted_stocks in __init__
old_init = '''        self.running = False'''
new_init = '''        self.running = False
        self.restricted_stocks = set()  # 處置股 (no day trading allowed)'''

if old_init in content:
    content = content.replace(old_init, new_init, 1)
    print("Added restricted_stocks to __init__")

# Load restricted stocks at start of scan
old_scan_start = '''        self.log.info("=" * 60)
        self.log.info("STEP 1: Scanning signals (Fugle real-time)...")'''

new_scan_start = '''        self.log.info("=" * 60)
        self.log.info("STEP 1: Scanning signals (Fugle real-time)...")

        # Load today's 處置股 list
        self.restricted_stocks = get_restricted_stocks()
        if self.restricted_stocks:
            self.log.info(f"  Loaded {len(self.restricted_stocks)} restricted stocks (處置/停牌)")'''

if old_scan_start in content:
    content = content.replace(old_scan_start, new_scan_start)
    print("Added restricted stocks loading to scan")

open(path, 'w', encoding='utf-8').write(content)
print("\nDone!")
