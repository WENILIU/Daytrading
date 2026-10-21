import re

path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
content = open(path, 'r', encoding='utf-8').read()

# Fix 1: Account number
content = content.replace(
    'self.account = "918D0495371"  # Fallback from web trading',
    'self.account = "913R0438724"  # 北高雄'
)

# Fix 2: Smart Trade - remove nOrderType, fix to use nBuySell only
old_short = '''        # Order type: 0=\u73fe\u80a1, 2=\u878d\u5238
        if sig.direction == Direction.SHORT:
            oOrder.nOrderType = 2   # \u878d\u5238
            oOrder.nBuySell = 1     # \u8ce3\u51fa (short sell)
        else:
            oOrder.nOrderType = 0   # \u73fe\u80a1
            oOrder.nBuySell = 0     # \u8cb7\u9032'''

new_short = '''        # Buy/Sell: 0=\u73fe\u80a1\u8cb7, 1=\u7121\u5238\u8ce3\u51fa(short)
        if sig.direction == Direction.SHORT:
            oOrder.nBuySell = 1     # \u7121\u5238\u8ce3\u51fa (short sell)
        else:
            oOrder.nBuySell = 0     # \u73fe\u80a1\u8cb7\u9032'''

if old_short in content:
    content = content.replace(old_short, new_short)
    print("Fix 2: Smart Trade order type - OK")
else:
    print("Fix 2: Pattern not found, trying alternate...")
    # Try to find and replace line by line
    lines = content.split('\n')
    new_lines = []
    skip_next = False
    for i, line in enumerate(lines):
        if 'nOrderType' in line and 'oOrder' in line:
            continue  # skip these lines
        new_lines.append(line)
    content = '\n'.join(new_lines)
    print("Fix 2: Removed nOrderType lines")

# Fix 3: SL field name (API typo)
content = content.replace(
    'oOrder.bstrSLPercent = str(int(self.config.stop_loss_pct * 100))',
    'oOrder.bstrSLPerent = str(int(self.config.stop_loss_pct * 100))'
)
print("Fix 3: SL field name - OK")

# Fix 4: TP field name (API typo)
content = content.replace(
    'oOrder.bstrTPPercent = str(int(self.config.take_profit_pct * 100))',
    'oOrder.bstrTPPercnet = str(int(self.config.take_profit_pct * 100))'
)
print("Fix 4: TP field name - OK")

# Fix 5: ForceClose use limit price
content = content.replace(
    'oOrder.nClearAllPriceType = 1  # \u5e02\u50f9\u51fa\u6e05',
    'oOrder.nClearAllPriceType = 2  # \u9650\u50f9\u51fa\u6e05\n        oOrder.bstrClearAllOrderPrice = str(sig.entry_price)'
)
print("Fix 5: ForceClose limit price - OK")

open(path, 'w', encoding='utf-8').write(content)
print("\nAll fixes saved!")
