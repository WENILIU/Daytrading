import pathlib

path = pathlib.Path(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py')
content = path.read_text(encoding='utf-8')

# Add "now" mode to the entry point
old_entry = '''if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "sim"
    config = Config()

    if mode == "live":
        print("LIVE MODE - Real orders via Capital SKCOM")
        print(f"  Account: {config.cust_cert_id}")
        print(f"  Capital: {config.capital:,.0f}")
        trader = GapFadeAutoTrader(config)
    elif mode == "sim":
        print("SIMULATION MODE - Paper trading via Fugle")
        print(f"  Capital: {config.capital:,.0f}")
        trader = GapFadeSimulator(config)
    else:
        print(f"Unknown mode: {mode}. Use: python gap_fade_auto.py [live|sim]")
        sys.exit(1)

    trader.run()'''

new_entry = '''class GapFadeNowTrader(GapFadeSimulator):
    """Immediate execution: skip time waits, run logic right now"""

    def run(self):
        self.running = True
        self.log.info("=" * 60)
        self.log.info("GAP FADE v3 NOW MODE (immediate, no time wait)")
        self.log.info(f"Capital: {self.config.capital:,.0f}")
        self.log.info(f"Time: {datetime.now().isoformat()}")

        try:
            self.connect()

            # Scan immediately
            self.scan_signals()

            if not self.signals:
                self.log.info("No signals right now. Done.")
                return

            # Confirm immediately (no 15-min wait)
            self.log.info("  [NOW] Skipping 15-min wait, confirming immediately...")
            self.confirm_and_enter()

            if not self.active_positions:
                self.log.info("No positions entered. Done.")
                return

            # Monitor with 30-min timeout (for testing)
            self.log.info("  [NOW] Monitoring for 30 min max...")
            self._monitor_now()

            self.daily_report()

        except KeyboardInterrupt:
            self.log.info("Interrupted.")
            self._force_close_all_sim(None)
        except Exception as e:
            self.log.error(f"FATAL: {e}", exc_info=True)
        finally:
            self.running = False
            self.disconnect()

    def _monitor_now(self):
        """Monitor for max 30 minutes"""
        from fugle_marketdata import RestClient
        client = RestClient(api_key=self.config.fugle_api_key)

        end_time = datetime.now().timestamp() + 1800  # 30 min

        while self.running and datetime.now().timestamp() < end_time:
            for symbol, sig in list(self.active_positions.items()):
                if sig.state not in (PositionState.FILLED, PositionState.MONITORING):
                    continue
                sig.state = PositionState.MONITORING

                try:
                    current = client.stock.intraday.current(symbol=symbol)
                    price = current.get("close", 0)
                except Exception:
                    continue

                should_exit = False
                reason = ""

                if sig.direction == Direction.SHORT:
                    if price >= sig.sl_price:
                        should_exit, reason = True, "STOP_LOSS"
                    elif price <= sig.tp_price:
                        should_exit, reason = True, "TAKE_PROFIT"
                else:
                    if price <= sig.sl_price:
                        should_exit, reason = True, "STOP_LOSS"
                    elif price >= sig.tp_price:
                        should_exit, reason = True, "TAKE_PROFIT"

                if should_exit:
                    self._close_sim(sig, price, reason)

            time.sleep(5)

        # Force close remaining
        self._force_close_all_sim(client)


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "sim"
    config = Config()

    if mode == "live":
        print("LIVE MODE - Real orders via Capital SKCOM")
        print(f"  Account: {config.cust_cert_id}")
        print(f"  Capital: {config.capital:,.0f}")
        trader = GapFadeAutoTrader(config)
    elif mode == "sim":
        print("SIMULATION MODE - Paper trading via Fugle (waits for 9:00/9:15)")
        print(f"  Capital: {config.capital:,.0f}")
        trader = GapFadeSimulator(config)
    elif mode == "now":
        print("NOW MODE - Immediate execution (no time wait, 30min monitor)")
        print(f"  Capital: {config.capital:,.0f}")
        trader = GapFadeNowTrader(config)
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python gap_fade_auto.py [live|sim|now]")
        sys.exit(1)

    trader.run()'''

if old_entry in content:
    content = content.replace(old_entry, new_entry)
    path.write_text(content, encoding='utf-8')
    print("Added NOW mode")
else:
    print("Pattern not found")
