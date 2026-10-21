import re

path = r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py"
content = open(path, "r", encoding="utf-8").read()

# 1. Add _wait_for_quotes call after _wait_until
old_call = '            self._wait_until("09:00")\n            self.scan_signals()'
new_call = '            self._wait_until("09:00")\n            self._wait_for_quotes(min_stocks=200, timeout_sec=10)\n            self.scan_signals()'
content = content.replace(old_call, new_call)

# 2. Add the _wait_for_quotes and _count_valid_quotes methods before _parse_time
anchor = '    @staticmethod\n    def _parse_time(time_str: str) -> datetime:'
new_methods = '''    def _wait_for_quotes(self, min_stocks: int = 200, timeout_sec: int = 10):
        """Wait until enough stocks have valid opening prices in local memory."""
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            count = self._count_valid_quotes()
            if count >= min_stocks:
                self.log.info(f"  Quotes ready: {count} stocks with valid prices")
                return
            self.log.info(f"  Waiting for quotes... ({count}/{min_stocks})")
            time.sleep(1)
        count = self._count_valid_quotes()
        self.log.warning(f"  Timeout: proceeding with {count} valid quotes")

    def _count_valid_quotes(self) -> int:
        """Quick count of stocks with valid open prices in local memory."""
        count = 0
        for market_no in [0, 1]:
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
                if pSKStock.nOpen > 0 and pSKStock.nRef > 0:
                    count += 1
                idx += 1
        return count

    @staticmethod
    def _parse_time(time_str: str) -> datetime:'''

content = content.replace(anchor, new_methods)

open(path, "w", encoding="utf-8").write(content)
print("Done: added _wait_for_quotes protection")
