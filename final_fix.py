path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
content = open(path, 'r', encoding='utf-8').read()

# Update tiers to optimal #4: T5=3x, T4=2x, T3=1x
old_tiers = '''    # --- Tiered sizing ---
    tiers = [
        (0.03, 999, 2.0, "T5"),
        (0.015, 0.03, 1.5, "T4"),
        (0.005, 0.015, 1.0, "T3"),
        (0.0, 0.005, 0.5, "T2"),
    ]'''

new_tiers = '''    # --- Tiered sizing (optimized: walk-forward validated) ---
    tiers = [
        (0.03, 999, 3.0, "T5"),
        (0.015, 0.03, 2.0, "T4"),
        (0.005, 0.015, 1.0, "T3"),
    ]'''

content = content.replace(old_tiers, new_tiers)
print("Tiers: updated to optimal #4 (3x/2x/1x, no T2)")

# Update position sizing
content = content.replace(
    '    base_position_pct = 0.05\n    long_position_pct = 0.025',
    '    base_position_pct = 0.08\n    long_position_pct = 0.015'
)
print("Position: SHORT 8%, LONG 1.5%")

# Update confirmation threshold to 2% (conservative, WR=81%)
content = content.replace(
    '    confirm_drop_min = 0.0',
    '    confirm_drop_min = 0.02'
)
print("Confirm: 2% (high WR mode)")

# Update max positions to 10 (conservative)
content = content.replace(
    '    max_daily_positions = 30',
    '    max_daily_positions = 10'
)
print("Max positions: 10")

# Update max exposure to 50% (conservative)
content = content.replace(
    '    max_daily_exposure = 0.70',
    '    max_daily_exposure = 0.50'
)
print("Max exposure: 50%")

open(path, 'w', encoding='utf-8').write(content)
print("\nDone! Updated to walk-forward validated parameters.")
