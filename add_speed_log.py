path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add a speed test log line in scan_signals after the scan completes
old = '        self.log.info(f"  Scan done in {scan_time:.2f}s. Found {len(signals)} signals, keeping top {len(self.signals)}:")'
new = '''        self.log.info(f"  Scan done in {scan_time:.3f}s ({total_stocks} stocks, {total_stocks/max(scan_time,0.001):.0f} stocks/sec)")
        self.log.info(f"  Found {len(signals)} signals, keeping top {len(self.signals)}:")'''

content = content.replace(old, new)

# Also add total_stocks counter (it's already there as idx increments, but let's track it)
old2 = '        # Scan via SKCOM GetStockByIndex (reads local memory, instant)\n        candidates = []'
new2 = '        # Scan via SKCOM GetStockByIndex (reads local memory, instant)\n        total_stocks = 0\n        candidates = []'

content = content.replace(old2, new2)

# Add total_stocks increment
old3 = '                idx += 1\n\n                # Skip invalid'
new3 = '                idx += 1\n                total_stocks += 1\n\n                # Skip invalid'

content = content.replace(old3, new3)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Added speed logging to scan.")
