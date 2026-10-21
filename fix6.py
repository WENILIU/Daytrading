path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
content = open(path, 'r', encoding='utf-8').read()

# Fix gap threshold: 3% -> 5%
content = content.replace(
    'gap_threshold = 0.03',
    'gap_threshold = 0.05'
)
print("gap_threshold: 0.03 -> 0.05")

# Fix stop loss: 6% -> 5%
content = content.replace(
    'stop_loss_pct = 0.06',
    'stop_loss_pct = 0.05'
)
print("stop_loss_pct: 0.06 -> 0.05")

# Fix take profit: 4% -> 5%
content = content.replace(
    'take_profit_pct = 0.04',
    'take_profit_pct = 0.05'
)
print("take_profit_pct: 0.04 -> 0.05")

# Fix max positions: 8 -> 30
content = content.replace(
    'max_daily_positions = 8',
    'max_daily_positions = 30'
)
print("max_daily_positions: 8 -> 30")

# Fix max exposure: 1.0 -> 0.70
content = content.replace(
    'max_daily_exposure = 1.0',
    'max_daily_exposure = 0.70'
)
print("max_daily_exposure: 1.0 -> 0.70")

open(path, 'w', encoding='utf-8').write(content)
print("\nAll parameters restored to validated values!")
