path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
content = open(path, 'r', encoding='utf-8').read()

# Disable LONG by setting long_position_pct to 0
content = content.replace(
    '    long_position_pct = 0.015',
    '    long_position_pct = 0.0  # DISABLED: LONG has WR 7% with confirmation filter'
)
print("LONG disabled (long_position_pct = 0)")

open(path, 'w', encoding='utf-8').write(content)
print("Saved.")
