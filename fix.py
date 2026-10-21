p = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\extend_2026.py'
with open(p, 'r', encoding='utf-8') as f:
    content = f.read()
old = "entry = sig['entry']"
new = "entry = sig['open']"
if old in content:
    content = content.replace(old, new)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Pattern not found')
    # Show what's there
    for i, line in enumerate(content.split('\n')):
        if 'entry = sig' in line:
            print(f'Line {i+1}: {line}')
