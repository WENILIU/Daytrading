path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
content = open(path, 'r', encoding='utf-8').read()

# Fix: Add nOrderPriceType = 2 after bstrOrderPrice line
old = '        oOrder.bstrOrderPrice = str(sig.entry_price)\n'
new = '        oOrder.bstrOrderPrice = str(sig.entry_price)\n        oOrder.nOrderPriceType = 2  # LIMIT\n'
content = content.replace(old, new, 1)
print("Added nOrderPriceType = 2")

# Fix: Revert SL field to correct spelling (struct has bstrSLPercent)
content = content.replace('oOrder.bstrSLPerent = ', 'oOrder.bstrSLPercent = ')
print("Fixed SL field name to bstrSLPercent")

# Fix: Revert TP field to correct spelling (struct has bstrTPPercent)
content = content.replace('oOrder.bstrTPPercnet = ', 'oOrder.bstrTPPercent = ')
print("Fixed TP field name to bstrTPPercent")

open(path, 'w', encoding='utf-8').write(content)
print("\nAll saved!")
