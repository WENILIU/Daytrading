with open("gap_fade_auto.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add model selection config
old_config = '''    # --- Position sizing: Model B (Market Regime Dynamic) ---
    # CAGR 165.1%, MDD -5.5%, WorstYr +9.1% (17yr, Walk-Forward validated)
    # Logic: size by market environment quality.
    # Deep drawdown + high vol + consecutive down = strongest mean-reversion edge.
    # Position range: 2%-10% per trade based on signal score.
    pos_min_pct = 0.02   # Minimum position (low-quality signals)
    pos_max_pct = 0.12   # Maximum position (highest-quality signals)
    base_position_pct = 0.05  # Fallback (unused, kept for compat)
    long_position_pct = 0.05  # Fallback (unused, kept for compat)'''

new_config = '''    # --- Position sizing: Model B/C (Market + Stock Regime Dynamic) ---
    # Model B: market-only. CAGR 165%, MDD -5.5% (WF validated)
    # Model C: market + stock. CAGR 208%, MDD -6.9% (WF validated, wins all windows)
    # Switch: "B" = market only, "C" = market + stock (recommended)
    position_model = "C"
    pos_min_pct = 0.02   # Minimum position (low-quality signals)
    pos_max_pct = 0.12   # Maximum position (highest-quality signals)
    base_position_pct = 0.05  # Fallback (unused, kept for compat)
    long_position_pct = 0.05  # Fallback (unused, kept for compat)'''

assert old_config in content, "Config not found"
content = content.replace(old_config, new_config)

# 2. Replace _calc_position_score with Model C version
old_score = '''    def _calc_position_score(self, sig) -> float:
        """Model B: Calculate position size (2-10%) from market regime + signal features."""
        mf = getattr(self, "_market_features", {})
        score = 0

        # Market drawdown (strongest factor)
        dd = mf.get("drawdown", 0)
        if dd < -0.10: score += 4
        elif dd < -0.05: score += 3
        elif dd < -0.03: score += 1

        # Market volatility (5d std)
        vol = mf.get("vol_5d", 0)
        if vol > 0.015: score += 3
        elif vol > 0.01: score += 1

        # Consecutive down days
        cd = mf.get("consec_down", 0)
        if cd >= 5: score += 3
        elif cd >= 3: score += 2
        elif cd >= 2: score += 1

        # 3-day market cumulative return
        r3 = mf.get("ret_3d", 0)
        if r3 < -0.05: score += 3
        elif r3 < -0.03: score += 2
        elif r3 < -0.01: score += 1

        # Signals today (high vol day = more opportunity)
        n_signals = len(self.signals)
        if n_signals >= 11: score += 2
        elif n_signals >= 8: score += 1

        # Day of week (Tue=1, Fri=4 are best)
        weekday = datetime.now().weekday()
        if weekday in [1, 4]: score += 1

        # Repeat signal (same stock had signal yesterday)
        if sig.symbol in getattr(self, "_yesterday_signals", set()):
            score += 1

        # Penalties
        month = datetime.now().month
        if month == 7: score -= 2
        if abs(sig.adj_gap) > 0.15: score -= 1

        # Map score to position percentage (PM4: validated via Walk-Forward)
        if score >= 10: return 0.12
        elif score >= 7: return 0.09
        elif score >= 5: return 0.07
        elif score >= 3: return 0.05
        elif score >= 1: return 0.04
        else: return 0.02'''

new_score = '''    def _calc_position_score(self, sig) -> float:
        """Model B/C: Calculate position size (2-12%) from market + stock regime."""
        mf = getattr(self, "_market_features", {})
        score = 0

        # === LAYER 1: Market Regime (Model B) ===
        # Market drawdown (strongest factor)
        dd = mf.get("drawdown", 0)
        if dd < -0.10: score += 4
        elif dd < -0.05: score += 3
        elif dd < -0.03: score += 1

        # Market volatility (5d std)
        vol = mf.get("vol_5d", 0)
        if vol > 0.015: score += 3
        elif vol > 0.01: score += 1

        # Consecutive down days
        cd = mf.get("consec_down", 0)
        if cd >= 5: score += 3
        elif cd >= 3: score += 2
        elif cd >= 2: score += 1

        # 3-day market cumulative return
        r3 = mf.get("ret_3d", 0)
        if r3 < -0.05: score += 3
        elif r3 < -0.03: score += 2
        elif r3 < -0.01: score += 1

        # Signals today (high vol day = more opportunity)
        n_signals = len(self.signals)
        if n_signals >= 11: score += 2
        elif n_signals >= 8: score += 1

        # Day of week (Tue=1, Fri=4 are best)
        weekday = datetime.now().weekday()
        if weekday in [1, 4]: score += 1

        # Repeat signal (same stock had signal yesterday)
        if sig.symbol in getattr(self, "_yesterday_signals", set()):
            score += 1

        # Penalties
        month = datetime.now().month
        if month == 7: score -= 2
        if abs(sig.adj_gap) > 0.15: score -= 1

        # === LAYER 2: Stock-Level (Model C only) ===
        if self.config.position_model == "C":
            # Stock trend: direction-aware
            stock_ret = getattr(sig, "stock_recent_ret", 0)  # Stock return between signals
            if sig.direction == Direction.LONG:
                if stock_ret < -0.05: score += 3  # Capitulation -> gap down = extreme
                elif stock_ret < -0.02: score += 2
            elif sig.direction == Direction.SHORT:
                if -0.02 <= stock_ret <= 0.02: score += 2  # Flat -> gap up = pure noise

            # Stock drawdown from recent high
            stock_dd = getattr(sig, "stock_drawdown", 0)
            if stock_dd < -0.15: score += 2
            elif stock_dd < -0.10: score += 1
            if stock_dd > 0: score -= 2  # At new high = real breakout, skip

            # Signal frequency (repeat pattern = reliable)
            freq = getattr(sig, "stock_signal_freq", 0)
            if 1 <= freq <= 4: score += 1
            elif freq >= 6: score -= 2

        # === MAP SCORE TO POSITION ===
        if score >= 10: return 0.12
        elif score >= 7: return 0.09
        elif score >= 5: return 0.07
        elif score >= 3: return 0.05
        elif score >= 1: return 0.04
        else: return 0.02'''

assert old_score in content, "Score function not found"
content = content.replace(old_score, new_score)

# 3. Add stock feature computation in scan_signals (after signals are created)
# Find where signals are sorted and add stock features
old_sort = '''        signals.sort(key=lambda s: abs(s.adj_gap), reverse=True)'''
new_sort = '''        # Compute stock-level features for Model C
        if self.config.position_model == "C":
            self._compute_stock_features(signals)

        signals.sort(key=lambda s: abs(s.adj_gap), reverse=True)'''

assert old_sort in content, "Sort line not found"
content = content.replace(old_sort, new_sort)

# 4. Add _compute_stock_features method (before _calc_position_score)
marker = "    def _calc_position_score(self, sig) -> float:"
stock_features_method = '''    def _compute_stock_features(self, signals):
        """Compute per-stock features for Model C scoring."""
        # Load stock history from yesterday_signals tracking
        # For live trading: track recent signals per stock
        if not hasattr(self, "_stock_history"):
            self._stock_history = {}  # {symbol: [(date, prev_close, direction), ...]}

        for sig in signals:
            sym = sig.symbol
            history = self._stock_history.get(sym, [])

            # Stock recent return: compare prev_close to last known close
            if history:
                last_close = history[-1][1]
                sig.stock_recent_ret = (sig.prev_close - last_close) / last_close
            else:
                sig.stock_recent_ret = 0.0

            # Stock drawdown from recent high
            if len(history) >= 2:
                recent_high = max(h[1] for h in history[-5:])
                sig.stock_drawdown = (sig.prev_close - recent_high) / recent_high
            else:
                sig.stock_drawdown = 0.0

            # Signal frequency in last 30 days
            from datetime import timedelta
            cutoff = datetime.now() - timedelta(days=30)
            freq = sum(1 for h in history if h[0] >= cutoff)
            sig.stock_signal_freq = freq

        # Update history with today's signals
        today = datetime.now()
        for sig in signals:
            sym = sig.symbol
            if sym not in self._stock_history:
                self._stock_history[sym] = []
            self._stock_history[sym].append((today, sig.prev_close, sig.direction))
            # Keep only last 60 days
            from datetime import timedelta
            cutoff = today - timedelta(days=60)
            self._stock_history[sym] = [h for h in self._stock_history[sym] if h[0] >= cutoff]

'''

assert marker in content, "Marker not found"
content = content.replace(marker, stock_features_method + marker)

with open("gap_fade_auto.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Model C integration done.")

import py_compile
try:
    py_compile.compile("gap_fade_auto.py", doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
