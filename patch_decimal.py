path = r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py"
content = open(path, "r", encoding="utf-8").read()

# Replace hardcoded /100.0 with dynamic decimal
old = """                open_price = pSKStock.nOpen / 100.0
                prev_close = pSKStock.nRef / 100.0"""

new = """                dec = pSKStock.sDecimal if pSKStock.sDecimal > 0 else 2
                divisor = 10 ** dec
                open_price = pSKStock.nOpen / divisor
                prev_close = pSKStock.nRef / divisor"""

if old in content:
    content = content.replace(old, new)
    open(path, "w", encoding="utf-8").write(content)
    print("Fixed: using dynamic sDecimal")
else:
    print("Pattern not found - checking actual code...")
    # Find the actual lines
    for i, line in enumerate(content.split('\n')):
        if 'nOpen' in line and '100' in line:
            print(f"  Line {i+1}: {line.strip()}")
