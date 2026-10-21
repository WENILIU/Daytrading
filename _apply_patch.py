import re

fpath = r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py"
with open(fpath, encoding="utf-8") as f:
    src = f.read()

# 1. Insert helper functions after Direction enum
anchor = 'class Direction(Enum):\n    SHORT = "SHORT"\n    LONG = "LONG"\n'
helpers = """

def get_tick_size(price: float) -> float:
    \"\"\"TWSE minimum tick size by price level.\"\"\"
    if price < 50:
        return 0.05
    elif price < 500:
        return 0.1
    elif price < 5000:
        return 0.5
    else:
        return 1.0


def calc_price_limits(prev_close: float) -> tuple:
    \"\"\"Calculate limit-up/limit-down from previous close.\"\"\"
    tick = get_tick_size(prev_close)
    limit_up = round(prev_close * 1.10 / tick) * tick
    limit_down = round(prev_close * 0.90 / tick) * tick
    return round(limit_up, 2), round(limit_down, 2)


def calc_effective_sl(entry: float, prev_close: float, direction,
                      base_sl_pct: float) -> tuple:
    \"\"\"Dynamic SL: min(normal SL, price_limit - 1 tick). Always reachable.\"\"\"
    limit_up, limit_down = calc_price_limits(prev_close)
    tick = get_tick_size(entry)

    if direction == Direction.SHORT:
        normal_sl = entry * (1 + base_sl_pct)
        limit_sl = limit_up - tick
        sl_price = min(normal_sl, limit_sl)
        sl_pct = (sl_price - entry) / entry
    else:
        normal_sl = entry * (1 - base_sl_pct)
        limit_sl = limit_down + tick
        sl_price = max(normal_sl, limit_sl)
        sl_pct = (entry - sl_price) / entry

    return round(sl_price, 2), max(0.01, sl_pct)

"""

if anchor in src:
    src = src.replace(anchor, anchor + helpers, 1)
    print("[1] Helper functions inserted")
else:
    print("[1] ERROR: anchor not found")

# 2. Replace fixed SL calculation with dynamic SL
old_sl = """            if sig.direction == Direction.SHORT:
                sig.sl_price = round(entry_price * (1 + self.config.stop_loss_pct), 1)
                sig.tp_price = round(entry_price * (1 - self.config.take_profit_pct), 1)
            else:
                sig.sl_price = round(entry_price * (1 - self.config.stop_loss_pct), 1)
                sig.tp_price = round(entry_price * (1 + self.config.take_profit_pct), 1)"""

new_sl = """            # Dynamic SL: capped by price limit (always reachable)
            sl_price, sl_pct = calc_effective_sl(
                entry_price, sig.prev_close, sig.direction,
                self.config.stop_loss_pct)
            sig.sl_price = sl_price
            sig._sl_pct = sl_pct  # store for Smart Trade

            if sig.direction == Direction.SHORT:
                sig.tp_price = round(entry_price * (1 - self.config.take_profit_pct), 1)
            else:
                sig.tp_price = round(entry_price * (1 + self.config.take_profit_pct), 1)"""

if old_sl in src:
    src = src.replace(old_sl, new_sl, 1)
    print("[2] Dynamic SL in signal generation")
else:
    print("[2] ERROR: SL block not found")

# 3. Replace fixed SL% in Smart Trade order
old_order = '        oOrder.bstrSLPercent = str(int(self.config.stop_loss_pct * 100))'
new_order = '        oOrder.bstrSLPercent = str(round(getattr(sig, "_sl_pct", self.config.stop_loss_pct) * 100, 1))'

if old_order in src:
    src = src.replace(old_order, new_order, 1)
    print("[3] Dynamic SL% in Smart Trade order")
else:
    print("[3] ERROR: order SL line not found")

# 4. Update log to show effective SL
old_log = '''            self.log.info(
                f"  ENTER {sig.symbol} {sig.direction.value} "
                f"price={entry_price} shares={shares} tier={sig.tier} "
                f"SL={sig.sl_price} TP={sig.tp_price}")'''

new_log = '''            limit_up, limit_down = calc_price_limits(sig.prev_close)
            self.log.info(
                f"  ENTER {sig.symbol} {sig.direction.value} "
                f"price={entry_price} shares={shares} tier={sig.tier} "
                f"SL={sig.sl_price}({getattr(sig, '_sl_pct', 0)*100:.1f}%) "
                f"TP={sig.tp_price} | limit={limit_up}/{limit_down}")'''

if old_log in src:
    src = src.replace(old_log, new_log, 1)
    print("[4] Updated log with price limit info")
else:
    print("[4] WARNING: log block not found (non-critical)")

with open(fpath, "w", encoding="utf-8") as f:
    f.write(src)
print("\nDone! gap_fade_auto.py updated.")
