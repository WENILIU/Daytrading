import pathlib

p = pathlib.Path(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py")
content = p.read_text(encoding="utf-8")

# Replace Yahoo scan_signals back to Fugle (real-time)
old_scan = '''    def scan_signals(self) -> list[Signal]:
        """9:00 scan all stocks for gap signals using Yahoo Finance batch API"""
        self.log.info("=" * 60)
        self.log.info("STEP 1: Scanning signals (Yahoo batch)...")

        # Get TAIEX market gap from ^TWII
        self.market_gap = self.yahoo.get_market_gap()
        self.log.info(f"  Market gap (TAIEX): {self.market_gap*100:+.2f}%")

        # Load stock list
        stock_codes = self.yahoo.load_stock_list(self.config.stock_list_path)
        if not stock_codes:
            self.log.error("  No stock list found!")
            return []
        self.log.info(f"  Scanning {len(stock_codes)} stocks...")

        # Batch scan via Yahoo
        t0 = time.time()
        raw_quotes = self.yahoo.scan_all(
            stock_codes,
            batch_size=self.config.yahoo_batch_size,
            max_workers=self.config.yahoo_max_workers)
        scan_time = time.time() - t0
        self.log.info(f"  Scan complete: {len(raw_quotes)} quotes in {scan_time:.1f}s")

        # Filter for gap signals
        candidates = []
        for q in raw_quotes:
            sym = q.get("symbol", "").replace(".TW", "")
            name = q.get("shortName", q.get("longName", "")) or ""
            price = q.get("regularMarketPrice", 0) or 0
            prev_close = q.get("regularMarketPreviousClose", 0) or 0

            if prev_close < self.config.min_price or prev_close > self.config.max_price:
                continue
            if price <= 0:
                continue

            raw_gap = (price - prev_close) / prev_close
            adj_gap = raw_gap - self.market_gap

            direction = None
            if adj_gap > self.config.gap_threshold:
                direction = Direction.SHORT
            elif adj_gap < -self.config.gap_threshold:
                direction = Direction.LONG

            if direction is None:
                continue

            candidates.append(Signal(
                symbol=sym, name=name[:8],
                direction=direction, open_price=price,
                prev_close=prev_close, raw_gap=raw_gap,
                adj_gap=adj_gap,
            ))

        candidates.sort(key=lambda s: abs(s.adj_gap), reverse=True)
        self.signals = candidates[:self.config.max_daily_positions]

        self.log.info(f"  Found {len(candidates)} total, keeping top {len(self.signals)}:")
        for s in self.signals:
            self.log.info(
                f"    {s.symbol} {s.name:<8} {s.direction.value:<5} "
                f"gap={s.adj_gap*100:+.1f}%")

        return self.signals'''

new_scan = '''    def scan_signals(self) -> list[Signal]:
        """9:00 scan all stocks for gap signals using Fugle (real-time)"""
        from fugle_marketdata import RestClient
        from concurrent.futures import ThreadPoolExecutor, as_completed

        self.log.info("=" * 60)
        self.log.info("STEP 1: Scanning signals (Fugle real-time)...")

        client = RestClient(api_key=self.config.fugle_api_key)
        stock = client.stock

        # Get market gap from TAIEX basket (real-time via Fugle)
        self.market_gap = 0.0
        try:
            basket = ["2330", "2317", "2454", "2303", "6505", "3711", "2412"]
            gaps = []
            for sym in basket:
                try:
                    q = stock.intraday.quote(symbol=sym)
                    op = q.get("openPrice") or 0
                    pc = q.get("previousClose") or 0
                    if pc > 0 and op > 0:
                        gaps.append((op - pc) / pc)
                except Exception:
                    pass
            if gaps:
                self.market_gap = sum(gaps) / len(gaps)
        except Exception:
            pass
        self.log.info(f"  Market gap: {self.market_gap*100:+.2f}%")

        # Get all stock symbols
        tickers = stock.intraday.tickers(
            type="EQUITY", exchange="TWSE", isNormal=True)
        symbols = [t["symbol"] for t in tickers.get("data", [])]
        self.log.info(f"  Scanning {len(symbols)} stocks (parallel)...")

        # Fetch quotes in parallel (10 threads)
        def fetch_quote(sym):
            try:
                q = stock.intraday.quote(symbol=sym)
                return {
                    "symbol": sym,
                    "name": q.get("name", ""),
                    "openPrice": q.get("openPrice") or 0,
                    "previousClose": q.get("previousClose") or 0,
                }
            except Exception:
                return None

        candidates = []
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_quote, s): s for s in symbols}
            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                if done_count % 300 == 0:
                    elapsed = time.time() - t0
                    self.log.info(f"    Progress: {done_count}/{len(symbols)} ({elapsed:.0f}s)")
                result = future.result()
                if result is None:
                    continue

                prev_close = result["previousClose"]
                open_price = result["openPrice"]

                if prev_close < self.config.min_price or prev_close > self.config.max_price:
                    continue
                if open_price <= 0:
                    continue

                raw_gap = (open_price - prev_close) / prev_close
                adj_gap = raw_gap - self.market_gap

                direction = None
                if adj_gap > self.config.gap_threshold:
                    direction = Direction.SHORT
                elif adj_gap < -self.config.gap_threshold:
                    direction = Direction.LONG

                if direction is None:
                    continue

                candidates.append(Signal(
                    symbol=result["symbol"], name=result["name"],
                    direction=direction, open_price=open_price,
                    prev_close=prev_close, raw_gap=raw_gap,
                    adj_gap=adj_gap,
                ))

        scan_time = time.time() - t0
        candidates.sort(key=lambda s: abs(s.adj_gap), reverse=True)
        self.signals = candidates[:self.config.max_daily_positions]

        self.log.info(f"  Scan done in {scan_time:.1f}s. Found {len(candidates)} total, keeping top {len(self.signals)}:")
        for s in self.signals:
            self.log.info(
                f"    {s.symbol} {s.name:<8} {s.direction.value:<5} "
                f"gap={s.adj_gap*100:+.1f}%")

        return self.signals'''

content = content.replace(old_scan, new_scan)

# Also restore fugle_api_key in Config (it was removed)
old_config = '''    # --- Yahoo Finance (for 9:00 scanning + monitoring) ---
    yahoo_batch_size = 50
    yahoo_max_workers = 15
    stock_list_path = Path(r"C:\\Users\\weni.liu\\Documents\\Codex\\2026-10-14\\new-chat-3\\outputs\\stock_1min_index.pkl")'''

new_config = '''    # --- Fugle (real-time scanning) ---
    fugle_api_key = "MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw=="

    # --- Yahoo Finance (post-market reporting only) ---
    yahoo_batch_size = 50
    yahoo_max_workers = 15
    stock_list_path = Path(r"C:\\Users\\weni.liu\\Documents\\Codex\\2026-10-14\\new-chat-3\\outputs\\stock_1min_index.pkl")'''

content = content.replace(old_config, new_config)

# Fix confirm_and_enter to use Fugle for real-time prices
old_confirm_batch = '''        # Batch fetch current prices for all signals at once
        symbols = [s.symbol for s in self.signals]
        quotes = self.yahoo.get_quotes(symbols)
        self.log.info(f"  Got quotes for {len(quotes)}/{len(symbols)} signals")

        total_exposure = 0

        for sig in self.signals:
            # Get current price from batch
            current_price = quotes.get(sig.symbol, {}).get("price", 0)
            if current_price <= 0:
                self.log.warning(f"  {sig.symbol}: no quote, skip")
                continue'''

new_confirm_batch = '''        # Get real-time prices via Fugle (only 5-8 stocks, instant)
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
                continue'''

content = content.replace(old_confirm_batch, new_confirm_batch)

# Fix get_price to use Fugle
old_getprice = '''    def get_price(self, stock_no: str) -> float:
        """Get current price via Yahoo Finance"""
        return self.yahoo.get_price(stock_no)

    def subscribe_quotes(self, stock_nos: list[str]):
        """No-op: Yahoo doesn't need subscription"""
        pass'''

new_getprice = '''    def get_price(self, stock_no: str) -> float:
        """Get current price via Fugle (real-time)"""
        from fugle_marketdata import RestClient
        try:
            client = RestClient(api_key=self.config.fugle_api_key)
            q = client.stock.intraday.quote(symbol=stock_no)
            return q.get("lastPrice") or 0.0
        except Exception:
            return 0.0

    def subscribe_quotes(self, stock_nos: list[str]):
        """No-op: Fugle quote() is on-demand"""
        pass'''

content = content.replace(old_getprice, new_getprice)

# Fix _monitor_now to use Fugle
old_monitor = '''    def _monitor_now(self):
        """Monitor for max 30 minutes using Yahoo quotes"""
        end_time = datetime.now().timestamp() + 1800  # 30 min

        while self.running and datetime.now().timestamp() < end_time:
            symbols = [s for s, sig in self.active_positions.items()
                       if sig.state in (PositionState.FILLED, PositionState.MONITORING)]
            if not symbols:
                break

            # Batch fetch all active positions in one call
            quotes = self.yahoo.get_quotes(symbols)

            for symbol, sig in list(self.active_positions.items()):
                if sig.state not in (PositionState.FILLED, PositionState.MONITORING):
                    continue
                sig.state = PositionState.MONITORING

                if symbol not in quotes:
                    continue
                price = quotes[symbol]["price"]
                if price <= 0:
                    continue'''

new_monitor = '''    def _monitor_now(self):
        """Monitor for max 30 minutes using Fugle (real-time)"""
        from fugle_marketdata import RestClient
        client = RestClient(api_key=self.config.fugle_api_key)
        end_time = datetime.now().timestamp() + 1800  # 30 min

        while self.running and datetime.now().timestamp() < end_time:
            symbols = [s for s, sig in self.active_positions.items()
                       if sig.state in (PositionState.FILLED, PositionState.MONITORING)]
            if not symbols:
                break

            for symbol, sig in list(self.active_positions.items()):
                if sig.state not in (PositionState.FILLED, PositionState.MONITORING):
                    continue
                sig.state = PositionState.MONITORING

                try:
                    q = client.stock.intraday.quote(symbol=symbol)
                    price = q.get("lastPrice") or 0
                except Exception:
                    continue
                if price <= 0:
                    continue'''

content = content.replace(old_monitor, new_monitor)

# Fix _force_close_all_sim to use Fugle
old_fc = '''    def _force_close_all_sim(self, client):
        symbols = [s for s, sig in self.active_positions.items()
                   if sig.state in (PositionState.FILLED, PositionState.MONITORING)]
        if not symbols:
            return
        quotes = self.yahoo.get_quotes(symbols)
        for symbol, sig in list(self.active_positions.items()):
            if sig.state not in (PositionState.FILLED, PositionState.MONITORING):
                continue
            price = quotes.get(symbol, {}).get("price", 0)
            if price <= 0:
                price = sig.entry_price
            self._close_sim(sig, price, "FORCE_CLOSE")'''

new_fc = '''    def _force_close_all_sim(self, client):
        from fugle_marketdata import RestClient
        fc_client = RestClient(api_key=self.config.fugle_api_key)
        for symbol, sig in list(self.active_positions.items()):
            if sig.state not in (PositionState.FILLED, PositionState.MONITORING):
                continue
            try:
                q = fc_client.stock.intraday.quote(symbol=symbol)
                price = q.get("lastPrice") or 0
            except Exception:
                price = 0
            if price <= 0:
                price = sig.entry_price
            self._close_sim(sig, price, "FORCE_CLOSE")'''

content = content.replace(old_fc, new_fc)

# Fix monitor_positions to use Fugle for reporting
old_mon_pos_quotes = '''            # Update prices for reporting (every 60s, lightweight)
            if int(now.timestamp()) % 60 < 5:
                symbols = [s for s, sig in self.active_positions.items()
                           if sig.state in (PositionState.FILLED, PositionState.MONITORING)]
                if symbols:
                    quotes = self.yahoo.get_quotes(symbols)
                    for sym in symbols:
                        if sym in quotes:
                            price = quotes[sym]["price"]
                            sig = self.active_positions[sym]'''

new_mon_pos_quotes = '''            # Update prices for reporting (every 60s, lightweight)
            if int(now.timestamp()) % 60 < 5:
                symbols = [s for s, sig in self.active_positions.items()
                           if sig.state in (PositionState.FILLED, PositionState.MONITORING)]
                if symbols:
                    from fugle_marketdata import RestClient
                    rc = RestClient(api_key=self.config.fugle_api_key)
                    for sym in symbols:
                        try:
                            q = rc.stock.intraday.quote(symbol=sym)
                            price = q.get("lastPrice") or 0
                        except Exception:
                            price = 0
                        if price <= 0:
                            continue
                        sig = self.active_positions[sym]'''

content = content.replace(old_mon_pos_quotes, new_mon_pos_quotes)

# Fix _force_close_all in live mode to use Fugle
old_force = '''    def _force_close_all(self):
        """Mark any remaining positions as force-closed (exchange already did it)"""
        symbols = [s for s, sig in self.active_positions.items()
                   if sig.state in (PositionState.FILLED, PositionState.MONITORING)]
        if not symbols:
            return
        quotes = self.yahoo.get_quotes(symbols)
        for symbol, sig in list(self.active_positions.items()):
            if sig.state not in (PositionState.FILLED, PositionState.MONITORING):
                continue
            price = quotes.get(symbol, {}).get("price", 0)
            if price <= 0:
                price = sig.entry_price
            self._mark_exit(sig, price, "FORCE_CLOSE")'''

new_force = '''    def _force_close_all(self):
        """Mark any remaining positions as force-closed (exchange already did it)"""
        from fugle_marketdata import RestClient
        symbols = [s for s, sig in self.active_positions.items()
                   if sig.state in (PositionState.FILLED, PositionState.MONITORING)]
        if not symbols:
            return
        rc = RestClient(api_key=self.config.fugle_api_key)
        for symbol, sig in list(self.active_positions.items()):
            if sig.state not in (PositionState.FILLED, PositionState.MONITORING):
                continue
            try:
                q = rc.stock.intraday.quote(symbol=symbol)
                price = q.get("lastPrice") or 0
            except Exception:
                price = 0
            if price <= 0:
                price = sig.entry_price
            self._mark_exit(sig, price, "FORCE_CLOSE")'''

content = content.replace(old_force, new_force)

# Update mode description
content = content.replace(
    'print("SIMULATION MODE - Paper trading via Yahoo (waits for 9:00/9:15)")',
    'print("SIMULATION MODE - Paper trading via Fugle (waits for 9:00/9:15)")')

p.write_text(content, encoding="utf-8")
print(f"Done. {len(content.splitlines())} lines")
