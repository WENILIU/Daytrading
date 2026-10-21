path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
content = open(path, 'r', encoding='utf-8').read()

# Fix ForceClose - find the line with nClearAllPriceType = 1
old = '        oOrder.nClearAllPriceType = 1  # \u5e02\u50f9\u51fa\u6e05'
new = '        oOrder.nClearAllPriceType = 2  # \u9650\u50f9\u51fa\u6e05\n        oOrder.bstrClearAllOrderPrice = str(sig.entry_price)'

if old in content:
    content = content.replace(old, new)
    print("Fixed ForceClose to use limit price")
else:
    # Try to find it by searching for the pattern
    import re
    pattern = r'(oOrder\.nClearAllPriceType\s*=\s*)1'
    match = re.search(pattern, content)
    if match:
        print(f"Found at position {match.start()}: {match.group()}")
        # Replace line by line
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'nClearAllPriceType' in line:
                print(f"Line {i+1}: {line}")
                lines[i] = '        oOrder.nClearAllPriceType = 2  # limit price'
                # Insert next line
                lines.insert(i+1, '        oOrder.bstrClearAllOrderPrice = str(sig.entry_price)')
                break
        content = '\n'.join(lines)
        print("Fixed via line-by-line approach")
    else:
        print("Pattern not found at all!")

open(path, 'w', encoding='utf-8').write(content)
print("Saved.")
