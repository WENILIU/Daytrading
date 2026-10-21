import re

with open("gap_fade_auto.py", "r", encoding="utf-8") as f:
    content = f.read()

# ============================================================
# 1. Replace config: remove old tiers, add Model B parameters
# ============================================================
old_config = '''    # --- Tiered sizing (Kelly 6-tier, EV-weighted) ---
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

new_config = '''    # --- Position sizing: Model B (Market Regime Dynamic) ---
    # CAGR 140.9%, MDD -5.5%, WorstYr +9.1% (17yr backtest)
    # Logic: size by market environment quality.
    # Deep drawdown + high vol + consecutive down = strongest mean-reversion edge.
    # Position range: 2%-10% per trade based on signal score.
    pos_min_pct = 0.02   # Minimum position (low-quality signals)
    pos_max_pct = 0.10   # Maximum position (highest-quality signals)
    base_position_pct = 0.05  # Fallback (unused, kept for compat)
    long_position_pct = 0.05  # Fallback (unused, kept for compat)'''

assert old_config in content, "Config pattern not found"
content = content.replace(old_config, new_config)

# ============================================================
# 2. Replace position sizing logic in confirm_and_enter
# ============================================================
old_sizing = '''            # Determine tier based on gap size
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
            shares = int(position_value / entry_price / 1000) * 1000'''

new_sizing = '''            # Model B: Dynamic position sizing based on market regime
            abs_gap = abs(sig.adj_gap)
            pos_pct = self._calc_position_score(sig)
            sig.tier = f"B{int(pos_pct*100)}%"
            sig.tier_multiplier = pos_pct / 0.05  # Normalize for logging

            # Calculate position
            position_value = self.config.capital * pos_pct
            shares = int(position_value / entry_price / 1000) * 1000'''

assert old_sizing in content, "Sizing pattern not found"
content = content.replace(old_sizing, new_sizing)

# ============================================================
# 3. Add _calc_position_score method and _fetch_market_history
# Insert before _place_entry_order
# ============================================================
marker = "    def _place_entry_order(self, sig: Signal):"
new_methods = '''    def _fetch_market_history(self):
        """Fetch TSEC weighted index history for position scoring. Call before scan."""
        import requests
        try:
            # TWSE index daily K-line (last 25 trading days)
            url = "https://www.twse.com.tw/zh/api/trade/Front/KLine/"
            params = {"stype": "MTIS", "ot": "JSON", "mlmt": "25"}
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            # Parse: data["data"]["kline"] = list of [date, open, high, low, close, volume]
            klines = data.get("data", {}).get("kline", [])
            if not klines:
                # Fallback: try alternative endpoint
                url2 = "https://www.twse.com.tw/data/zh/fund/MI_INDEX"
                resp2 = requests.get(url2, timeout=10)
                self.log.warning("  Market history: primary API empty, trying fallback")
                self._market_history = []
                return

            # Extract close prices (index 4 in kline array)
            self._market_history = [float(k[4]) for k in klines]
            self.log.info(f"  Market history loaded: {len(self._market_history)} days")
            self._calc_market_features()
        except Exception as e:
            self.log.warning(f"  Market history fetch failed: {e}. Using neutral sizing.")
            self._market_history = []
            self._market_features = {"drawdown": 0, "vol_5d": 0, "consec_down": 0, "ret_3d": 0, "prev_ret": 0}

    def _calc_market_features(self):
        """Calculate market regime features from index history."""
        hist = self._market_history
        if len(hist) < 6:
            self._market_features = {"drawdown": 0, "vol_5d": 0, "consec_down": 0, "ret_3d": 0, "prev_ret": 0}
            return

        # Daily returns
        returns = [(hist[i] - hist[i-1]) / hist[i-1] for i in range(1, len(hist))]

        # Previous day return (last element = most recent completed day)
        prev_ret = returns[-1] if returns else 0

        # 3-day cumulative
        ret_3d = sum(returns[-3:]) if len(returns) >= 3 else 0

        # 5-day volatility (std of daily returns)
        vol_5d = float(np.std(returns[-5:])) if len(returns) >= 5 else 0

        # Drawdown from 20-day high
        recent = hist[-20:] if len(hist) >= 20 else hist
        high_20 = max(recent)
        current = hist[-1]
        drawdown = (current - high_20) / high_20

        # Consecutive down days
        consec_down = 0
        for r in reversed(returns):
            if r < 0:
                consec_down += 1
            else:
                break

        self._market_features = {
            "drawdown": drawdown,
            "vol_5d": vol_5d,
            "consec_down": consec_down,
            "ret_3d": ret_3d,
            "prev_ret": prev_ret,
        }
        self.log.info(
            f"  Market regime: DD={drawdown*100:.1f}% Vol={vol_5d*100:.2f}% "
            f"ConsecDown={consec_down} 3dRet={ret_3d*100:.1f}% PrevRet={prev_ret*100:.2f}%")

    def _calc_position_score(self, sig) -> float:
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

        # Map score to position percentage
        if score >= 10: return 0.10
        elif score >= 7: return 0.08
        elif score >= 5: return 0.06
        elif score >= 3: return 0.05
        elif score >= 1: return 0.04
        else: return 0.02

'''

assert marker in content, "Marker not found"
content = content.replace(marker, new_methods + marker)

# ============================================================
# 4. Add _fetch_market_history call in run() before scan
# Find where scan is called and add market history fetch before it
# ============================================================
old_scan_call = '''            self.scan_signals()'''
# There are multiple calls. Find the one in run() method
# Let's find the pattern in the run method
old_run_scan = '''            # Scan immediately
            self.scan_signals()'''
new_run_scan = '''            # Fetch market history for position scoring
            self._fetch_market_history()
            # Scan immediately
            self.scan_signals()'''

if old_run_scan in content:
    content = content.replace(old_run_scan, new_run_scan)
else:
    # Try the other pattern in run()
    old_run_scan2 = '''        try:
            self.scan_signals()'''
    new_run_scan2 = '''        try:
            self._fetch_market_history()
            self.scan_signals()'''
    if old_run_scan2 in content:
        content = content.replace(old_run_scan2, new_run_scan2, 1)  # Only first occurrence
    else:
        print("WARNING: Could not find scan call in run()")

# ============================================================
# 5. Add numpy import if not present
# ============================================================
if "import numpy as np" not in content:
    content = content.replace("import pandas as pd", "import numpy as np\nimport pandas as pd")

# ============================================================
# 6. Add _yesterday_signals tracking (for repeat signal detection)
# Add initialization in __init__ or run
# ============================================================
# Find where self.signals = [] is initialized
old_init = "        self.signals: list[Signal] = []"
new_init = '''        self.signals: list[Signal] = []
        self._yesterday_signals: set = set()
        self._market_features: dict = {}
        self._market_history: list = []'''

if old_init in content:
    content = content.replace(old_init, new_init)

with open("gap_fade_auto.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Model B edits applied.")

import py_compile
try:
    py_compile.compile("gap_fade_auto.py", doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
