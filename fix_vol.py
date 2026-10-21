path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace volume filter config
old = "    min_volume_t1 = 5_000_000"
new = "    min_dollar_volume_t1 = 10_000_000  # T-1 turnover >= 10M TWD"
content = content.replace(old, new)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated volume filter to dollar-based (10M TWD turnover)")
