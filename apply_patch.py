import re

path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# === 1. Update Config ===
old_config = """    # --- Confirmation (9:15) ---
    confirm_wait_minutes = 15
    confirm_drop_min = 0.025

    # --- Tiered sizing (optimized: walk-forward validated) ---
    tiers = [
        (0.03, 999, 3.0, "T5"),
        (0.015, 0.03, 2.0, "T4"),
        (0.005, 0.015, 1.0, "T3"),
    ]

    # --- Position sizing ---
    base_position_pct = 0.08
    long_position_pct = 0.0  # DISABLED: LONG has WR 7% with confirmation filter

    # --- Exit ---
    stop_loss_pct = 0.05
    take_profit_pct = 0.05
    force_exit_time = "13:25"

    # --- Limits ---
    max_daily_positions = 10
    max_daily_exposure = 0.50"""

new_config = """    # --- Entry: 9:00 immediate (no confirmation wait) ---
    confirm_wait_minutes = 0
    confirm_drop_min = 0.0  # No confirmation needed

    # --- Tiered sizing (gap-based, Plan B) ---
    tiers = [
        (0.07, 999, 1.5, "T5"),   # gap > 7%: 1.5x position
        (0.05, 0.07, 1.0, "T3"),  # gap 5-7%: 1.0x position
    ]

    # --- Position sizing (Plan B: CAGR~108%, MDD~-1.7%) ---
    base_position_pct = 0.05
    long_position_pct = 0.05  # LONG enabled

    # --- Exit ---
    stop_loss_pct = 0.06
    take_profit_pct = 0.04
    force_exit_time = "13:25"

    # --- Limits ---
    max_daily_positions = 15
    max_daily_exposure = 0.70"""

content = content.replace(old_config, new_config)

# === 2. Update run() flow: skip 9:15 wait ===
old_run = """            self._wait_until("09:00")
            self.scan_signals()

            if not self.signals:
                self.log.info("No signals. Done.")
                return

            self._wait_until("09:15")
            self.confirm_and_enter()"""

new_run = """            self._wait_until("09:00")
            self.scan_signals()

            if not self.signals:
                self.log.info("No signals. Done.")
                return

            # Enter immediately at open (no confirmation wait)
            self.confirm_and_enter()"""

content = content.replace(old_run, new_run)

# === 3. Update confirm_and_enter: use open_price, gap-based tiers ===
old_confirm = """    def confirm_and_enter(self):
        \"\"\"9:15 confirm signals and auto-place orders\"\"\"
        self.log.info("=" * 60)
        self.log.info("STEP 2: Confirming & placing orders...")

        # Get real-time prices via Fugle (only 5-8 stocks, instant)
        from fugle_marketdata import RestClient
        client = RestClient(api_key=self.config.fugle_api_key)
        symbols = [s.symbol for s in self.signals]

        total_exposure = 0

        for sig in self.signals:
            # Get current price via Fugle (real-time)
            try:
                q = client.stock.intraday.quote(symbol=sig.symbol)
                current_price = q.get("lastPrice") or 0
            except Exception:
                current_price = 0
            if current_price <= 0:
                self.log.warning(f"  {sig.symbol}: no quote, skip")
                continue

            # Calculate 15-min move
            if sig.direction == Direction.SHORT:
                drop_pct = (sig.open_price - current_price) / sig.open_price
            else:
                drop_pct = (current_price - sig.open_price) / sig.open_price

            # Check confirmation
            if drop_pct <= self.config.confirm_drop_min:
                self.log.info(
                    f"  {sig.symbol}: NOT confirmed (move={drop_pct*100:+.2f}%), SKIP")
                sig.state = PositionState.CANCELLED
                continue

            # Determine tier
            for min_drop, max_drop, mult, label in self.config.tiers:
                if min_drop <= drop_pct < max_drop:
                    sig.tier = label
                    sig.tier_multiplier = mult
                    break

            if sig.tier == "":
                continue

            # Calculate position
            if sig.direction == Direction.SHORT:
                base_value = self.config.capital * self.config.base_position_pct
            else:
                base_value = self.config.capital * self.config.long_position_pct

            position_value = base_value * sig.tier_multiplier
            shares = int(position_value / current_price / 1000) * 1000

            if shares < 1000:
                self.log.info(f"  {sig.symbol}: < 1 zhang, SKIP")
                continue

            # Check exposure limit
            actual_value = shares * current_price
            if total_exposure + actual_value > self.config.capital * self.config.max_daily_exposure:
                self.log.info(f"  {sig.symbol}: exposure limit, SKIP")
                continue

            total_exposure += actual_value

            # Set entry/SL/TP
            sig.entry_price = current_price
            sig.shares = shares

            if sig.direction == Direction.SHORT:
                sig.sl_price = round(current_price * (1 + self.config.stop_loss_pct), 1)
                sig.tp_price = round(current_price * (1 - self.config.take_profit_pct), 1)
            else:
                sig.sl_price = round(current_price * (1 - self.config.stop_loss_pct), 1)
                sig.tp_price = round(current_price * (1 + self.config.take_profit_pct), 1)

            # Place order
            self._place_entry_order(sig)

        self.log.info(
            f"  Total exposure: {total_exposure:,.0f} "
            f"({total_exposure/self.config.capital*100:.0f}%)")"""

new_confirm = """    def confirm_and_enter(self):
        \"\"\"Enter immediately at open price (no confirmation wait)\"\"\"
        self.log.info("=" * 60)
        self.log.info("STEP 2: Placing orders at open...")

        total_exposure = 0

        for sig in self.signals:
            # Use open price as entry (immediate execution at market open)
            entry_price = sig.open_price

            # Determine tier based on gap size
            abs_gap = abs(sig.adj_gap)
            for min_gap, max_gap, mult, label in self.config.tiers:
                if min_gap <= abs_gap < max_gap:
                    sig.tier = label
                    sig.tier_multiplier = mult
                    break

            if sig.tier == "":
                continue

            # Calculate position
            if sig.direction == Direction.SHORT:
                base_value = self.config.capital * self.config.base_position_pct
            else:
                base_value = self.config.capital * self.config.long_position_pct

            position_value = base_value * sig.tier_multiplier
            shares = int(position_value / entry_price / 1000) * 1000

            if shares < 1000:
                self.log.info(f"  {sig.symbol}: < 1 zhang, SKIP")
                continue

            # Check exposure limit
            actual_value = shares * entry_price
            if total_exposure + actual_value > self.config.capital * self.config.max_daily_exposure:
                self.log.info(f"  {sig.symbol}: exposure limit, SKIP")
                continue

            total_exposure += actual_value

            # Set entry/SL/TP
            sig.entry_price = entry_price
            sig.shares = shares

            if sig.direction == Direction.SHORT:
                sig.sl_price = round(entry_price * (1 + self.config.stop_loss_pct), 1)
                sig.tp_price = round(entry_price * (1 - self.config.take_profit_pct), 1)
            else:
                sig.sl_price = round(entry_price * (1 - self.config.stop_loss_pct), 1)
                sig.tp_price = round(entry_price * (1 + self.config.take_profit_pct), 1)

            self.log.info(
                f"  ENTER {sig.symbol} {sig.direction.value} "
                f"price={entry_price} shares={shares} tier={sig.tier} "
                f"SL={sig.sl_price} TP={sig.tp_price}")

            # Place order
            self._place_entry_order(sig)

        self.log.info(
            f"  Total exposure: {total_exposure:,.0f} "
            f"({total_exposure/self.config.capital*100:.0f}%)")"""

content = content.replace(old_confirm, new_confirm)

# === 4. Update NOW mode (skip wait) ===
old_now = """            # Confirm immediately (no 15-min wait)
            self.log.info("  [NOW] Skipping 15-min wait, confirming immediately...")
            self.confirm_and_enter()"""

new_now = """            # Enter immediately
            self.log.info("  [NOW] Entering at open price...")
            self.confirm_and_enter()"""

content = content.replace(old_now, new_now)

# === 5. Update header comment ===
content = content.replace(
    "Gap Fade v3 AUTO - Full Auto Trading System (Capital Securities / SKCOM)",
    "Gap Fade v3 AUTO - Plan B (CAGR~108%, MDD~-1.7%) | Capital Securities / SKCOM"
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated gap_fade_auto.py with Plan B parameters.")
print("Changes:")
print("  - Entry: 9:00 immediate (no 9:15 wait)")
print("  - Direction: SHORT + LONG")
print("  - SL: 6%, TP: 4%")
print("  - Position: 5% base, 7.5% for gap>7%")
print("  - Max: 15 positions/day, 70% exposure")
print("  - Tiers: gap-based (not price-drop-based)")
