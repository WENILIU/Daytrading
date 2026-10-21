path = r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py"
content = open(path, "r", encoding="utf-8").read()

old = '''    # --- Tiered sizing (gap-based, Plan B) ---
    tiers = [
        (0.07, 999, 1.5, "T5"),   # gap > 7%: 1.5x position
        (0.05, 0.07, 1.0, "T3"),  # gap 5-7%: 1.0x position
    ]

    # --- Position sizing (Plan B: CAGR~108%, MDD~-1.7%) ---
    base_position_pct = 0.05
    long_position_pct = 0.05  # LONG enabled'''

new = '''    # --- Tiered sizing (Kelly 6-tier, EV-weighted) ---
    # CAGR 175%, MDD -2.0%, Sharpe 11.25 (450M + lot constraints)
    # Logic: size by expected value, NOT win rate.
    # Large gaps have lower WR but higher EV per trade -> deserve more position.
    tiers = [
        (0.09, 999, 2.5, "K6"),   # gap > 9%: 2.5x (EV 1.41%)
        (0.08, 0.09, 2.0, "K5"),  # gap 8-9%: 2.0x (EV 1.37%)
        (0.07, 0.08, 1.8, "K4"),  # gap 7-8%: 1.8x (EV 1.22%)
        (0.065, 0.07, 1.5, "K3"), # gap 6.5-7%: 1.5x (EV 1.13%)
        (0.06, 0.065, 1.2, "K2"), # gap 6-6.5%: 1.2x (EV 1.00%)
        (0.05, 0.06, 1.0, "K1"),  # gap 5-6%: 1.0x (EV 0.75%)
    ]

    # --- Position sizing (Kelly 6-tier: CAGR~175%, MDD~-2.0%) ---
    base_position_pct = 0.05
    long_position_pct = 0.05  # LONG enabled'''

if old in content:
    content = content.replace(old, new)
    open(path, "w", encoding="utf-8").write(content)
    print("Done: updated to Kelly 6-tier")
else:
    print("ERROR: pattern not found")
    # Debug
    for i, line in enumerate(content.split('\n')):
        if 'Tiered sizing' in line or 'Plan B' in line:
            print(f"  Found at line {i+1}: {line.strip()}")
