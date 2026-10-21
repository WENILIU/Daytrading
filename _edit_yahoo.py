with open("gap_fade_auto.py", "r", encoding="utf-8") as f:
    content = f.read()

old_fetch = '''    def _fetch_market_history(self):
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
            self._market_features = {"drawdown": 0, "vol_5d": 0, "consec_down": 0, "ret_3d": 0, "prev_ret": 0}'''

new_fetch = '''    def _fetch_market_history(self):
        """Fetch TSEC weighted index history via Yahoo Finance. Call before scan."""
        import requests
        try:
            # Yahoo Finance: ^TWII = TWSE Capitalization Weighted Index
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII"
            params = {"range": "1mo", "interval": "1d"}
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()
            result = data["chart"]["result"][0]
            raw_closes = result["indicators"]["quote"][0]["close"]
            # Filter out None values
            self._market_history = [c for c in raw_closes if c is not None]
            if len(self._market_history) < 6:
                self.log.warning("  Market history: insufficient data (%d days)" % len(self._market_history))
                self._market_features = {"drawdown": 0, "vol_5d": 0, "consec_down": 0, "ret_3d": 0, "prev_ret": 0}
                return
            self.log.info(f"  Market history loaded: {len(self._market_history)} days (Yahoo ^TWII)")
            self._calc_market_features()
        except Exception as e:
            self.log.warning(f"  Market history fetch failed: {e}. Using neutral sizing.")
            self._market_history = []
            self._market_features = {"drawdown": 0, "vol_5d": 0, "consec_down": 0, "ret_3d": 0, "prev_ret": 0}'''

assert old_fetch in content, "Fetch pattern not found"
content = content.replace(old_fetch, new_fetch)

with open("gap_fade_auto.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Updated to Yahoo Finance.")

import py_compile
try:
    py_compile.compile("gap_fade_auto.py", doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
