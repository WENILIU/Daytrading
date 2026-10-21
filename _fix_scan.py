import pathlib

path = pathlib.Path(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py')
content = path.read_text(encoding='utf-8')

# Replace the scan_signals method with a working version using quote() + threading
old_scan = '''    def scan_signals(self) -> list[Signal]:
        """9:00 scan all stocks for gap signals"""
        from fugle_marketdata import RestClient

        self.log.info("=" * 60)
        self.log.info("STEP 1: Scanning signals...")

        client = RestClient(api_key=self.config.fugle_api_key)
        stock = client.stock

        # Get TAIEX gap
        try:
            index_data = stock.intraday.current(symbol="0000")
            self.market_gap = index_data.get("changePercent", 0) / 100
        except Exception:
            self.market_gap = 0.0

        self.log.info(f"  Market gap: {self.market_gap*100:+.2f}%")

        # Get all tickers
        tickers = stock.intraday.tickers(
            type="EQUITY", exchange="TWSE", isNormal=True)

        candidates = []
        for ticker in tickers["data"]:
            symbol = ticker["symbol"]
            name = ticker["name"]
            open_price = ticker.get("open", 0)
            prev_close = ticker.get("previousClose", 0)

            if prev_close < self.config.min_price or prev_close > self.config.max_price:
                continue

            raw_gap = (open_price - prev_close) / prev_close if prev_close > 0 else 0
            adj_gap = raw_gap - self.market_gap

            direction = None
            if adj_gap > self.config.gap_threshold:
                direction = Direction.SHORT
            elif adj_gap < -self.config.gap_threshold:
                direction = Direction.LONG

            if direction is None:
                continue

            candidates.append(Signal(
                symbol=symbol, name=name, direction=direction,
                open_price=open_price, prev_close=prev_close,
                raw_gap=raw_gap, adj_gap=adj_gap,
            ))

        candidates.sort(key=lambda s: abs(s.adj_gap), reverse=True)
        self.signals = candidates[:self.config.max_daily_positions]

        self.log.info(f"  Found {len(self.signals)} signals:")
        for s in self.signals:
            self.log.info(
                f"    {s.symbol} {s.name:<8} {s.direction.value:<5} "
                f"gap={s.adj_gap*100:+.1f}%")

        return self.signals'''

new_scan = '''    def scan_signals(self) -> list[Signal]:
        """9:00 scan all stocks for gap signals using quote() API"""
        from fugle_marketdata import RestClient
        from concurrent.futures import ThreadPoolExecutor, as_completed

        self.log.info("=" * 60)
        self.log.info("STEP 1: Scanning signals...")

        client = RestClient(api_key=self.config.fugle_api_key)
        stock = client.stock

        # Get TAIEX gap via quote
        try:
            idx_data = stock.intraday.quote(symbol="0000")
            self.market_gap = (idx_data.get("changePercent", 0) or 0) / 100
        except Exception:
            self.market_gap = 0.0

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
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_quote, s): s for s in symbols}
            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                if done_count % 300 == 0:
                    self.log.info(f"    Progress: {done_count}/{len(symbols)}")
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

        candidates.sort(key=lambda s: abs(s.adj_gap), reverse=True)
        self.signals = candidates[:self.config.max_daily_positions]

        self.log.info(f"  Found {len(self.signals)} signals:")
        for s in self.signals:
            self.log.info(
                f"    {s.symbol} {s.name:<8} {s.direction.value:<5} "
                f"gap={s.adj_gap*100:+.1f}%")

        return self.signals'''

if old_scan in content:
    content = content.replace(old_scan, new_scan)
    path.write_text(content, encoding='utf-8')
    print("Fixed scan_signals with parallel quote()")
else:
    print("Pattern not found - need manual fix")
