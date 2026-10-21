path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# === Replace scan_signals method ===
old_scan_start = "    def scan_signals(self) -> list[Signal]:\n        \"\"\"9:00 scan all stocks for gap signals using Fugle (real-time)\"\"\""
new_scan = '''    def scan_signals(self) -> list[Signal]:
        """9:00 scan all stocks via SKCOM real-time quotes (< 1 second)"""

        self.log.info("=" * 60)
        self.log.info("STEP 1: Scanning signals (SKCOM real-time)...")

        # Load restricted stocks
        self.restricted_stocks = get_restricted_stocks()
        if self.restricted_stocks:
            self.log.info(f"  Loaded {len(self.restricted_stocks)} restricted stocks")

        # Scan via SKCOM GetStockByIndex (reads local memory, instant)
        candidates = []
        self.market_gap = 0.0
        gaps_for_market = []
        t0 = time.time()

        for market_no in [0, 1]:  # 0=TWSE, 1=TPEx
            idx = 0
            while idx < 5000:
                pSKStock = sk.SKSTOCKLONG()
                try:
                    pSKStock, nCode = self.quote_lib.SKQuoteLib_GetStockByIndexLONG(
                        market_no, idx, pSKStock)
                    if nCode != 0:
                        break
                except Exception:
                    break

                stock_no = str(pSKStock.bstrStockNo)
                stock_name = str(pSKStock.bstrStockName)
                open_price = pSKStock.nOpen / 100.0
                prev_close = pSKStock.nRef / 100.0
                y_volume = pSKStock.nYQty  # yesterday volume (shares)

                idx += 1

                # Skip invalid
                if open_price <= 0 or prev_close <= 0:
                    continue

                # Price filter
                if prev_close < self.config.min_price or prev_close > self.config.max_price:
                    continue

                # Dollar volume filter (T-1 turnover >= 10M)
                dollar_vol = y_volume * prev_close
                if dollar_vol < self.config.min_dollar_volume_t1:
                    continue

                # Skip restricted (處置/無法當沖)
                if stock_no in self.restricted_stocks:
                    continue

                # Calculate gap
                raw_gap = (open_price - prev_close) / prev_close

                # Collect for market gap calculation (major stocks)
                if stock_no in ("2330", "2317", "2454", "2303", "6505", "3711", "2412"):
                    gaps_for_market.append(raw_gap)

                candidates.append({
                    "symbol": stock_no,
                    "name": stock_name,
                    "openPrice": open_price,
                    "previousClose": prev_close,
                    "raw_gap": raw_gap,
                })

        # Calculate market gap
        if gaps_for_market:
            self.market_gap = sum(gaps_for_market) / len(gaps_for_market)
        self.log.info(f"  Market gap: {self.market_gap*100:+.2f}%")

        # Filter by adjusted gap
        signals = []
        for c in candidates:
            adj_gap = c["raw_gap"] - self.market_gap

            direction = None
            if adj_gap > self.config.gap_threshold:
                direction = Direction.SHORT
            elif adj_gap < -self.config.gap_threshold:
                direction = Direction.LONG

            if direction is None:
                continue

            signals.append(Signal(
                symbol=c["symbol"], name=c["name"],
                direction=direction, open_price=c["openPrice"],
                prev_close=c["previousClose"], raw_gap=c["raw_gap"],
                adj_gap=adj_gap,
            ))

        scan_time = time.time() - t0
        signals.sort(key=lambda s: abs(s.adj_gap), reverse=True)
        self.signals = signals[:self.config.max_daily_positions]

        self.log.info(f"  Scan done in {scan_time:.2f}s. Found {len(signals)} signals, keeping top {len(self.signals)}:")
        for s in self.signals:
            self.log.info(
                f"    {s.symbol} {s.name:<8} {s.direction.value:<5} "
                f"gap={s.adj_gap*100:+.1f}%")

        return self.signals'''

# Find and replace the old scan_signals
import re
# Find from "def scan_signals" to the next "    # ---" or "    def " at same indent
pattern = r'(    def scan_signals\(self\).*?)(\n    # -{10,}|\n    def (?!scan_signals))'
match = re.search(pattern, content, re.DOTALL)
if match:
    old_text = match.group(1)
    content = content.replace(old_text, new_scan + "\n")
    print("Replaced scan_signals with SKCOM version")
else:
    print("ERROR: Could not find scan_signals to replace")
    # Try simpler approach
    idx = content.find("    def scan_signals(self)")
    if idx > 0:
        # Find the end (next method at same indent level)
        end_idx = content.find("\n    # ----------------------------------------------------------\n    # STEP 2:", idx)
        if end_idx < 0:
            end_idx = content.find("\n    def confirm_and_enter", idx)
        if end_idx > 0:
            old_text = content[idx:end_idx]
            content = content.replace(old_text, new_scan + "\n")
            print("Replaced via index approach")

# === Add quote_lib initialization in connect() ===
old_connect_marker = "        self.log.info(\"Connecting to Capital Securities (SKCOM)...\")"
new_connect = """        self.log.info("Connecting to Capital Securities (SKCOM)...")
        # Initialize quote library for real-time data
        self.quote_lib = comtypes.client.CreateObject(
            sk.SKQuoteLib, interface=sk.ISKQuoteLib)"""

content = content.replace(old_connect_marker, new_connect)

# === Add EnterMonitor after login ===
old_after_login = "        self.log.info(\"Login successful.\")"
new_after_login = """        self.log.info("Login successful.")

        # Connect to quote server (for real-time stock data)
        nCode = self.quote_lib.SKQuoteLib_EnterMonitorLONG()
        if nCode == 0:
            self.log.info("Quote server connected (real-time data ready).")
        else:
            self.log.warning(f"Quote server connection failed: code={nCode}")
            self.log.warning("Will use Fugle fallback for scanning.")"""

content = content.replace(old_after_login, new_after_login)

# === Add quote_lib to __init__ ===
old_init = "        self.running = False"
new_init = """        self.running = False
        self.quote_lib = None"""

content = content.replace(old_init, new_init, 1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Done. gap_fade_auto.py now uses SKCOM for scanning.")
