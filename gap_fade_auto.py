"""
Gap Fade v3 AUTO - Plan B (CAGR~108%, MDD~-1.7%) | Capital Securities / SKCOM
=========================================================================
Broker: Capital Securities (群益金鼎) via SKCOM COM API
Capital: 4.5M TWD
Mode: 9:00 scan -> 9:15 auto-entry -> real-time SL/TP -> 13:25 force close

Prerequisites:
  1. Install SKCOM: run regsvr32 on SKCOM.dll (done)
  2. pip install comtypes
  3. Fill in your credentials below

Version: 2026-10-18
"""

import time
import json
import logging
import ctypes
import requests
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np
import comtypes.client

# Load SKCOM
SKCOM_PATH = r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll"
comtypes.client.GetModule(SKCOM_PATH)
import comtypes.gen.SKCOMLib as sk


# ============================================================
# CONFIG
# ============================================================


def get_restricted_stocks() -> set:
    """Get today's disposal stocks (cannot do day trading).
    Uses finlab etl:disposal_stock_filter if available, else exchange API."""
    restricted = set()
    
    # Method 1: finlab (most reliable)
    try:
        from finlab import data as fdata
        from datetime import date
        today = date.today().strftime('%Y%m%d')
        disposal_df = fdata.get('etl:disposal_stock_filter', as_of=today)
        if disposal_df is not None and len(disposal_df) > 0:
            # Get the latest date row
            latest_date = disposal_df.index[-1]
            row = disposal_df.loc[latest_date]
            # False = IS disposal (cannot trade)
            disposal_stocks = row[~row].index.tolist()
            restricted.update(disposal_stocks)
    except Exception:
        pass
    
    # Method 2: Exchange API fallback
    if not restricted:
        try:
            import requests
            url = "https://www.twse.com.tw/zh/api/tradingReference/stockRestriction"
            resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code == 200:
                data = resp.json()
                for row in data.get('data', []):
                    if len(row) >= 2:
                        restricted.add(str(row[1]).strip())
        except Exception:
            pass
    
    # Always exclude known non-day-trade stocks
    restricted.update(['2330', '2317'])
    
    return restricted


def get_borrowable_stocks() -> set | None:
    """Get stocks eligible for short-selling (securities lending available).
    Returns None if data unavailable (skip filter)."""
    try:
        from finlab import data as fdata
        lfv = fdata.get('etl:lending_fee_volume')
        borrowable = set()
        for stock in lfv.columns:
            if (lfv[stock] > 0).any():
                borrowable.add(stock)
        return borrowable
    except Exception:
        return None



class Config:
    # --- Capital Securities credentials ---
    cust_cert_id = "D121280815"       # 身分證字號
    password = "Zaq582811@"         # 下單密碼

    # --- Capital ---
    capital = 4_500_000

    # --- Signal detection (9:00) ---
    gap_threshold = 0.05
    min_price = 30
    max_price = 225
    min_dollar_volume_t1 = 3_000_000  # T-1 turnover >= 3M TWD

    # --- Entry: 9:00 immediate (no confirmation wait) ---
    confirm_wait_minutes = 0
    confirm_drop_min = 0.0  # No confirmation needed

    # --- Position sizing: Model B/C (Market + Stock Regime Dynamic) ---
    # Model B: market-only. CAGR 165%, MDD -5.5% (WF validated)
    # Model C: market + stock. CAGR ~99%, MDD -5.2% (with 處置+借券+流動性 filters)
    # Switch: "B" = market only, "C" = market + stock (recommended)
    position_model = "C"
    pos_min_pct = 0.02   # Minimum position (low-quality signals)
    pos_max_pct = 0.12   # Maximum position (highest-quality signals)
    base_position_pct = 0.05  # Fallback (unused, kept for compat)
    long_position_pct = 0.05  # Fallback (unused, kept for compat)

    # --- Exit ---
    stop_loss_pct = 0.05
    take_profit_pct = 0.12  # TP for strong signals (score >= threshold)
    take_profit_low_pct = 0.07  # TP for weak signals (score < threshold, same as baseline)
    tp_score_threshold = 3  # Score cutoff for TP switch
    force_exit_time = "13:25"

    # --- Limits ---
    max_daily_positions = 15
    max_daily_exposure = 0.75  # 5% signals cap
    max_total_exposure = 1.50  # Total cap including 3-5% signals (requires margin)

    # --- 3-5% Gap Module (activates only during market drawdown) ---
    gap_threshold_low = 0.03   # Lower gap threshold
    mkt_dd_threshold = -0.05   # Only scan 3-5% when market drawdown < -5%
    pos_low_pct = 0.05         # Flat position for 3-5% signals

    # --- Cost ---
    cost_per_trade = 0.00109  # 0.2%%x1.7折 + 當沖稅減半

    # --- Fugle (real-time scanning) ---
    fugle_api_key = "MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw=="

    # --- Yahoo Finance (post-market reporting only) ---
    yahoo_batch_size = 50
    yahoo_max_workers = 15
    stock_list_path = Path(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\valid_stocks.txt")

    # --- Logging ---
    log_dir = Path(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\trading_logs")


# ============================================================
# DATA STRUCTURES
# ============================================================

class Direction(Enum):
    SHORT = "SHORT"
    LONG = "LONG"


def get_tick_size(price: float) -> float:
    """TWSE minimum tick size by price level."""
    if price < 50:
        return 0.05
    elif price < 500:
        return 0.1
    elif price < 5000:
        return 0.5
    else:
        return 1.0


def calc_price_limits(prev_close: float) -> tuple:
    """Calculate limit-up/limit-down from previous close."""
    tick = get_tick_size(prev_close)
    limit_up = round(prev_close * 1.10 / tick) * tick
    limit_down = round(prev_close * 0.90 / tick) * tick
    return round(limit_up, 2), round(limit_down, 2)


def calc_effective_sl(entry: float, prev_close: float, direction,
                      base_sl_pct: float) -> tuple:
    """Dynamic SL: min(normal SL, price_limit - 1 tick). Always reachable."""
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



class PositionState(Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    ORDERED = "ORDERED"
    FILLED = "FILLED"
    MONITORING = "MONITORING"
    EXITED = "EXITED"
    CANCELLED = "CANCELLED"


@dataclass
class Signal:
    symbol: str
    name: str
    direction: Direction
    open_price: float
    prev_close: float
    raw_gap: float
    adj_gap: float
    state: PositionState = PositionState.PENDING
    tier: str = ""
    tier_multiplier: float = 0.0
    shares: int = 0
    entry_price: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    order_seq: str = ""
    fill_price: float = 0.0
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl: float = 0.0
    zhangting: float = 0.0
    dieding: float = 0.0
    is_at_limit: bool = False
    is_low_gap: bool = False




# ============================================================
# YAHOO FINANCE QUOTE CLIENT
# ============================================================

class YahooQuoteClient:
    """Batch real-time quotes from Yahoo Finance (free, no API key needed)"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20, pool_maxsize=30)
        self.session.mount("https://", adapter)
        self.crumb = ""
        self._connected = False

    def connect(self):
        """Get session cookie + crumb for authenticated requests"""
        try:
            self.session.get("https://fc.yahoo.com", timeout=5, allow_redirects=True)
            r = self.session.get(
                "https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=5)
            self.crumb = r.text.strip()
            if self.crumb:
                self._connected = True
                return True
        except Exception:
            pass
        return False

    def _fetch_batch(self, codes: list[str]) -> list[dict]:
        """Fetch one batch of quotes (max ~50 per request)"""
        symbols = ",".join([f"{s}.TW" for s in codes])
        url = (f"https://query1.finance.yahoo.com/v7/finance/quote"
               f"?symbols={symbols}&crumb={self.crumb}")
        try:
            r = self.session.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                return data.get("quoteResponse", {}).get("result", [])
        except Exception:
            pass
        return []

    def scan_all(self, stock_codes: list[str], batch_size=50,
                 max_workers=15) -> list[dict]:
        """Scan all stocks in parallel batches. Returns list of quote dicts."""
        if not self._connected:
            self.connect()

        batches = [stock_codes[i:i+batch_size]
                   for i in range(0, len(stock_codes), batch_size)]
        all_results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._fetch_batch, b) for b in batches]
            for future in as_completed(futures):
                all_results.extend(future.result())

        return all_results

    def get_quotes(self, codes: list[str]) -> dict[str, dict]:
        """Get current quotes for specific stocks. Returns {code: {price, prev_close}}"""
        if not self._connected:
            self.connect()

        results = self._fetch_batch(codes)
        quotes = {}
        for q in results:
            sym = q.get("symbol", "").replace(".TW", "")
            price = q.get("regularMarketPrice", 0) or 0
            prev = q.get("regularMarketPreviousClose", 0) or 0
            if price > 0:
                quotes[sym] = {"price": price, "prev_close": prev}
        return quotes

    def get_price(self, code: str) -> float:
        """Get single stock current price"""
        quotes = self.get_quotes([code])
        if code in quotes:
            return quotes[code]["price"]
        return 0.0

    def get_market_gap(self) -> float:
        """Get TAIEX (^TWII) gap percentage"""
        if not self._connected:
            self.connect()
        try:
            url = (f"https://query1.finance.yahoo.com/v7/finance/quote"
                   f"?symbols=%5ETWII&crumb={self.crumb}")
            r = self.session.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                results = data.get("quoteResponse", {}).get("result", [])
                if results:
                    price = results[0].get("regularMarketPrice", 0) or 0
                    prev = results[0].get("regularMarketPreviousClose", 0) or 0
                    if prev > 0 and price > 0:
                        return (price - prev) / prev
        except Exception:
            pass
        return 0.0

    def load_stock_list(self, path: Path) -> list[str]:
        """Load stock codes from pickle index"""
        import pickle
        if path.exists():
            with open(path, "rb") as f:
                idx = pickle.load(f)
            return list(idx.keys())
        return []


# ============================================================
# TRADING ENGINE (SKCOM)
# ============================================================

class GapFadeAutoTrader:
    def __init__(self, config: Config):
        self.config = config
        self.m_pSKCenter = None
        self.m_pSKOrder = None
        self.m_pSKQuote = None
        self.m_pSKReply = None
        self.account = ""
        self.user_id = config.cust_cert_id
        self.yahoo = YahooQuoteClient()
        self.signals: list[Signal] = []
        self._yesterday_signals: set = set()
        self._market_features: dict = {}
        self._market_history: list = []
        self.active_positions: dict[str, Signal] = {}
        self.closed_trades: list[dict] = []
        self.running = False
        self.quote_lib = None
        self.restricted_stocks = set()  # 處置股 (no day trading allowed)
        self.market_gap = 0.0
        self.market_drawdown = 0.0
        self._logged_in = False

        # Setup logging
        config.log_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = config.log_dir / f"trading_{today}.log"

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(log_file, encoding="utf-8"),
                logging.StreamHandler()
            ]
        )
        self.log = logging.getLogger("GapFade")

    # ----------------------------------------------------------
    # CONNECTION (SKCOM)
    # ----------------------------------------------------------

    def connect(self):
        """Login to Capital Securities via SKCOM"""
        self.log.info("Connecting to Capital Securities (SKCOM)...")
        # Initialize quote library for real-time data
        self.quote_lib = comtypes.client.CreateObject(
            sk.SKQuoteLib, interface=sk.ISKQuoteLib)

        # Create COM objects
        self.m_pSKCenter = comtypes.client.CreateObject(
            sk.SKCenterLib, interface=sk.ISKCenterLib)
        self.m_pSKOrder = comtypes.client.CreateObject(
            sk.SKOrderLib, interface=sk.ISKOrderLib)
        self.m_pSKQuote = comtypes.client.CreateObject(
            sk.SKQuoteLib, interface=sk.ISKQuoteLib)
        self.m_pSKReply = comtypes.client.CreateObject(
            sk.SKReplyLib, interface=sk.ISKReplyLib)

        # Register ReplyLib event FIRST (required before login)
        class SKReplyLibEvent:
            def OnReplyMessage(self, bstrUserID, bstrMessages):
                self_ref = self
                self_ref.log.info(f"  [Reply] {bstrUserID}: {bstrMessages[:100]}")
                return -1

        reply_event = SKReplyLibEvent()
        reply_event.log = self.log
        self._reply_handler = comtypes.client.GetEvents(
            self.m_pSKReply, reply_event)

        # Set production environment
        self.m_pSKCenter.SKCenterLib_SetAuthority(0)

        # Login
        nCode = self.m_pSKCenter.SKCenterLib_Login(
            self.config.cust_cert_id, self.config.password)
        msg = self.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
        if nCode != 0:
            raise ConnectionError(f"Login failed: {msg}")
        self.log.info(f"Login OK: {msg}")

        # Connect to quote server (real-time stock data for scanning)
        nCode = self.quote_lib.SKQuoteLib_EnterMonitorLONG()
        if nCode == 0:
            self.log.info("Quote server connected. Real-time data ready.")
        else:
            msg2 = self.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
            self.log.warning(f"Quote server failed: {msg2}")
        self._logged_in = True

        # Initialize order system
        self.m_pSKOrder.SKOrderLib_Initialize()

        # Read certificate (required for placing orders)
        nCert = self.m_pSKOrder.ReadCertByID(self.config.cust_cert_id)
        if nCert != 0:
            self.log.warning(f"ReadCertByID returned {nCert}, orders may fail")
        else:
            self.log.info("Certificate verified OK")

        # Register OrderLib events (OnAccount, OnOrderResult, OnFill, OnCancel)
        def make_order_event(trader_ref):
            class OLE:
                def OnAccount(self_inner, *args):
                    try:
                        data = args[1] if len(args) > 1 else str(args)
                        parts = data.split(",")
                        if len(parts) >= 4 and parts[0] == "TS":
                            branch = parts[1]
                            acct_num = parts[3]
                            full = f"{branch}{acct_num}"
                            trader_ref.log.info(f"  [Account detected] {full}")
                            if not trader_ref.account:
                                trader_ref.account = full
                    except Exception as e:
                        trader_ref.log.warning(f"  [OnAccount] parse error: {e}")
                    return -1
                def OnOrderResult(self_inner, *args):
                    trader_ref.log.info(f"  [OrderResult] {args}")
                    return -1
                def OnFill(self_inner, *args):
                    trader_ref.log.info(f"  [FILL] {args}")
                    return -1
                def OnCancel(self_inner, *args):
                    trader_ref.log.info(f"  [CANCEL] {args}")
                    return -1
                def OnOpen(self_inner, *args):
                    return -1
            return OLE()

        self._order_handler = comtypes.client.GetEvents(
            self.m_pSKOrder, make_order_event(self))

        # Get trading account
        self.m_pSKOrder.GetUserAccount()
        time.sleep(2)  # Wait for OnAccount callback

        if not self.account:
            # Try to get account directly
            self.log.warning("Account not received via callback, trying direct query...")
            # The account should be in format: brokerID + accountNo
            self.account = "913R0438724"  # 北高雄

        self.log.info(f"Account: {self.account}")

        # Connect Yahoo for quotes
        if self.yahoo.connect():
            self.log.info("  Yahoo Finance connected (quotes ready)")
        else:
            self.log.warning("  Yahoo Finance connection failed, will retry on use")

        self.log.info("Connected. Ready to trade.")

    def disconnect(self):
        if self._logged_in:
            self.log.info("Disconnected.")
            self._logged_in = False

    # ----------------------------------------------------------
    # QUOTE: Get current price via SKQuoteLib
    # ----------------------------------------------------------

    def get_price(self, stock_no: str) -> float:
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
        pass

    # ----------------------------------------------------------
    # ORDER: Place stock order via SKOrderLib
    # ----------------------------------------------------------

    def send_order(self, stock_no: str, buy_sell: int, flag: int,
                   price: float, qty: int, trade_type: int = 0) -> tuple:
        """
        Place a stock order.
        buy_sell: 0=Buy, 1=Sell
        flag: 0=現股, 2=融券(放空)
        price: limit price
        qty: number of shares
        trade_type: 0=ROD, 1=IOC, 2=FOK
        Returns (message, code)
        """
        pOrder = sk.STOCKORDER()
        pOrder.bstrFullAccount = self.account
        pOrder.bstrStockNo = stock_no
        pOrder.sPrime = 0          # 上市上櫃
        pOrder.sPeriod = 0         # 盤中
        pOrder.sFlag = flag        # 0=現股, 2=融券
        pOrder.sBuySell = buy_sell # 0=買進, 1=賣出
        pOrder.bstrPrice = str(price)
        pOrder.nQty = qty
        pOrder.nTradeType = trade_type
        pOrder.nSpecialTradeType = 2  # 限價

        bstrMessage, nCode = self.m_pSKOrder.SendStockOrder(
            self.user_id, False, pOrder)
        return bstrMessage, nCode

    # ----------------------------------------------------------
    # STEP 1: 9:00 SCAN (Fugle API for bulk speed)
    # ----------------------------------------------------------

    def _calc_market_drawdown(self) -> float:
        """Calculate 20-day market drawdown from 0050."""
        try:
            import yfinance as yf
            idx = yf.Ticker("0050.TW")
            hist = idx.history(period="1mo")
            if len(hist) < 10:
                return 0.0
            current = hist['Close'].iloc[-1]
            rolling_max = hist['Close'].max()
            dd = (current - rolling_max) / rolling_max
            self.log.info(f"  Market drawdown: {dd*100:.1f}%")
            return dd
        except Exception as e:
            self.log.warning(f"  Market drawdown calc failed: {e}")
            return 0.0

    def scan_signals(self) -> list[Signal]:
        """9:00 scan all stocks via TWSE public API (~5 seconds, free, no auth)."""

        self.log.info("=" * 60)
        self.log.info("STEP 1: Scanning signals (TWSE API)...")

        # Load restricted stocks
        self.restricted_stocks = get_restricted_stocks()
        self.borrowable_stocks = get_borrowable_stocks()
        if self.borrowable_stocks:
            self.log.info(f"  Borrowable stocks: {len(self.borrowable_stocks)}")
        if self.restricted_stocks:
            self.log.info(f"  Loaded {len(self.restricted_stocks)} restricted stocks")

        # Load stock list
        stock_list = self._load_stock_list()
        self.log.info(f"  Stock universe: {len(stock_list)} codes")

        # TWSE API batch scan
        t0 = time.time()
        raw_data = self._twse_batch_scan(stock_list)
        scan_time = time.time() - t0
        self.log.info(f"  TWSE scan: {len(raw_data)} quotes in {scan_time:.1f}s")

        # Process: filter + gap detection
        total_valid = 0
        candidates = []
        self.market_gap = 0.0
        gaps_for_market = []

        for item in raw_data:
            try:
                stock_no = item.get("c", "")
                stock_name = item.get("n", "")
                o_str = item.get("o", "-")
                y_str = item.get("y", "-")
                v_str = item.get("v", "0")

                if o_str == "-" or y_str == "-":
                    continue
                open_price = float(o_str)
                prev_close = float(y_str)
                volume = int(float(v_str)) if v_str and v_str != "-" else 0

                if open_price <= 0 or prev_close <= 0:
                    continue

                total_valid += 1

                # Price filter
                if prev_close < self.config.min_price or prev_close > self.config.max_price:
                    continue

                # Dollar volume filter (auction volume x price >= threshold)
                dollar_vol = volume * open_price
                if dollar_vol < self.config.min_dollar_volume_t1:
                    continue

                # Skip restricted (處置股)
                if stock_no in self.restricted_stocks:
                    continue

                # Skip non-borrowable stocks (cannot short-sell)
                if self.borrowable_stocks is not None and stock_no not in self.borrowable_stocks:
                    continue

                # Calculate gap
                raw_gap = (open_price - prev_close) / prev_close

                # Market gap from major stocks
                if stock_no in ("2330", "2317", "2454", "2303", "6505", "3711", "2412"):
                    gaps_for_market.append(raw_gap)

                candidates.append({
                    "symbol": stock_no,
                    "name": stock_name,
                    "openPrice": open_price,
                    "previousClose": prev_close,
                    "raw_gap": raw_gap,
                })
            except (ValueError, TypeError):
                continue

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

        # Calculate price limits and mark at-limit signals
        for sig in signals:
            lu, ld = calc_price_limits(sig.prev_close)
            sig.zhangting = lu
            sig.dieding = ld
            if sig.direction == Direction.SHORT and abs(sig.open_price - lu) < 0.01:
                sig.is_at_limit = True
            elif sig.direction == Direction.LONG and abs(sig.open_price - ld) < 0.01:
                sig.is_at_limit = True

        # --- 3-5% Gap Module (only during market drawdown) ---
        self.market_drawdown = self._calc_market_drawdown()
        if self.market_drawdown < self.config.mkt_dd_threshold:
            self.log.info(f"  Market DD {self.market_drawdown*100:.1f}% < {self.config.mkt_dd_threshold*100:.0f}%: scanning 3-5% gaps")
            low_signals = []
            for c in candidates:
                adj_gap = c["raw_gap"] - self.market_gap
                if self.config.gap_threshold_low <= abs(adj_gap) < self.config.gap_threshold:
                    direction = Direction.SHORT if adj_gap > 0 else Direction.LONG
                    sig = Signal(
                        symbol=c["symbol"], name=c["name"],
                        direction=direction, open_price=c["openPrice"],
                        prev_close=c["previousClose"], raw_gap=c["raw_gap"],
                        adj_gap=adj_gap,
                    )
                    sig.is_low_gap = True
                    lu, ld = calc_price_limits(sig.prev_close)
                    sig.zhangting = lu
                    sig.dieding = ld
                    low_signals.append(sig)
            self.log.info(f"  3-5% signals found: {len(low_signals)}")
            signals.extend(low_signals)
        else:
            self.log.info(f"  Market DD {self.market_drawdown*100:.1f}%: 3-5% module OFF")

        # Compute stock-level features for Model C
        if self.config.position_model == "C":
            self._compute_stock_features(signals)

        signals.sort(key=lambda s: abs(s.adj_gap), reverse=True)
        self.signals = signals[:self.config.max_daily_positions]

        self.log.info(f"  Scan done in {time.time()-t0:.1f}s ({total_valid} valid quotes)")
        self.log.info(f"  Found {len(signals)} signals, keeping top {len(self.signals)}:")
        for s in self.signals:
            self.log.info(
                f"    {s.symbol} {s.name:<8} {s.direction.value:<5} "
                f"gap={s.adj_gap*100:+.1f}%")

        return self.signals

    def _load_stock_list(self) -> list[str]:
        """Load stock codes from valid_stocks.txt."""
        path = self.config.stock_list_path
        if not path.exists():
            self.log.warning(f"  Stock list not found: {path}")
            path = path.parent / "all_stocks.txt"
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def _twse_batch_scan(self, stock_list: list[str]) -> list[dict]:
        """Batch-query TWSE API. 100 codes/request, 15 parallel workers."""
        TWSE_API = "http://mis.twse.com.tw/stock/api/getStockInfo.jsp"
        BATCH_SIZE = 100
        MAX_WORKERS = 15

        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        adapter = requests.adapters.HTTPAdapter(pool_connections=25, pool_maxsize=25)
        session.mount("http://", adapter)

        def query_batch(codes):
            parts = [f"tse_{c}.tw" for c in codes]
            ex_ch = "|".join(parts)
            url = f"{TWSE_API}?ex_ch={ex_ch}&_={int(time.time()*1000)}"
            try:
                r = session.get(url, timeout=8)
                if r.status_code != 200:
                    return []
                text = r.text.strip()
                idx = text.find("{")
                if idx < 0:
                    return []
                return json.loads(text[idx:]).get("msgArray", [])
            except Exception:
                return []

        batches = [stock_list[i:i+BATCH_SIZE] for i in range(0, len(stock_list), BATCH_SIZE)]
        all_raw = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(query_batch, b) for b in batches]
            for f in as_completed(futures):
                all_raw.extend(f.result())

        return all_raw


    # ----------------------------------------------------------
    # STEP 2: 9:15 CONFIRM + AUTO ORDER
    # ----------------------------------------------------------

    def confirm_and_enter(self):
        """Enter all signals immediately. Skip stocks at daily price limit."""
        self.log.info("=" * 60)
        self.log.info("STEP 2: Placing orders at open...")

        total_exposure = 0

        skipped_at_limit = 0

        for sig in self.signals:
            if sig.is_at_limit:
                skipped_at_limit += 1
                continue

            # Use open price as entry (immediate execution at market open)
            entry_price = sig.open_price

            # Position sizing: Model C for 5%+, flat for 3-5%
            abs_gap = abs(sig.adj_gap)
            if getattr(sig, 'is_low_gap', False):
                pos_pct = self.config.pos_low_pct
                sig.tier = f"LOW{int(pos_pct*100)}%"
            else:
                pos_pct = self._calc_position_score(sig)
                sig.tier = f"B{int(pos_pct*100)}%"
            sig.tier_multiplier = pos_pct / 0.05  # Normalize for logging

            # Calculate position
            position_value = self.config.capital * pos_pct
            shares = int(position_value / entry_price / 1000) * 1000

            if shares < 1000:
                self.log.info(f"  {sig.symbol}: < 1 zhang, SKIP")
                continue

            # Check exposure limit
            actual_value = shares * entry_price
            cap = self.config.max_total_exposure if getattr(sig, 'is_low_gap', False) else self.config.max_daily_exposure
            if total_exposure + actual_value > self.config.capital * cap:
                self.log.info(f"  {sig.symbol}: exposure limit, SKIP")
                continue

            total_exposure += actual_value

            # Set entry/SL/TP
            sig.entry_price = entry_price
            sig.shares = shares

            # Dynamic SL: capped by price limit (always reachable)
            sl_price, sl_pct = calc_effective_sl(
                entry_price, sig.prev_close, sig.direction,
                self.config.stop_loss_pct)
            sig.sl_price = sl_price
            sig._sl_pct = sl_pct  # store for Smart Trade

            tp_pct = self._get_tp_pct(sig)
            if sig.direction == Direction.SHORT:
                sig.tp_price = round(entry_price * (1 - tp_pct), 1)
            else:
                sig.tp_price = round(entry_price * (1 + tp_pct), 1)
            sig._tp_pct = tp_pct

            limit_up, limit_down = calc_price_limits(sig.prev_close)
            self.log.info(
                f"  ENTER {sig.symbol} {sig.direction.value} "
                f"price={entry_price} shares={shares} tier={sig.tier} "
                f"SL={sig.sl_price}({getattr(sig, '_sl_pct', 0)*100:.1f}%) "
                f"TP={sig.tp_price}({getattr(sig, '_tp_pct', 0)*100:.0f}%) | limit={limit_up}/{limit_down}")

            # Place order
            self._place_entry_order(sig)

        if skipped_at_limit:
            self.log.info(f"  Skipped (at price limit): {skipped_at_limit}")
        self.log.info(
            f"  Total exposure: {total_exposure:,.0f} "
            f"({total_exposure/self.config.capital*100:.0f}%)")

    def _fetch_market_history(self):
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

    def _compute_stock_features(self, signals):
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

    def _calc_position_score(self, sig) -> float:
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

        # Store raw score for TP calculation
        sig._score = score

        # === MAP SCORE TO POSITION ===
        if score >= 10: return 0.12
        elif score >= 7: return 0.09
        elif score >= 5: return 0.07
        elif score >= 3: return 0.05
        elif score >= 1: return 0.04
        else: return 0.02

    def _get_tp_pct(self, sig) -> float:
        """Score-based dynamic TP: weak signals TP=7%, strong signals TP=12%."""
        score = getattr(sig, '_score', 0)
        if score < self.config.tp_score_threshold:
            return self.config.take_profit_low_pct
        return self.config.take_profit_pct

    def _place_entry_order(self, sig: Signal):
        """Place Smart Trade order (entry + SL + TP + ForceClose in one shot)"""
        oOrder = sk.STOCKSTRATEGYORDER()
        oOrder.bstrFullAccount = self.account
        oOrder.bstrStockNo = sig.symbol
        oOrder.nQty = sig.shares
        oOrder.bstrOrderPrice = str(sig.entry_price)
        oOrder.nOrderPriceType = 2  # LIMIT

        # Buy/Sell: 0=現股買, 1=無券賣出(short)
        if sig.direction == Direction.SHORT:
            oOrder.nBuySell = 1     # 無券賣出 (short sell)
        else:
            oOrder.nBuySell = 0     # 現股買進

        # Stop Loss (percentage-based, auto-triggered by exchange)
        oOrder.nStopLossFlag = 1
        oOrder.nRDOSLPercent = 1
        oOrder.bstrSLPercent = str(round(getattr(sig, "_sl_pct", self.config.stop_loss_pct) * 100, 1))
        oOrder.nRDSLMarketPriceType = 1  # 市價觸發

        # Take Profit (percentage-based)
        oOrder.nTakeProfitFlag = 1
        oOrder.nRDOTPPercent = 1
        oOrder.bstrTPPercent = str(int(getattr(sig, "_tp_pct", self.config.take_profit_pct) * 100))
        oOrder.nRDTPMarketPriceType = 1  # 市價觸發

        # Force close at 13:25
        oOrder.nClearAllFlag = 1
        oOrder.bstrClearCancelTime = "1325"
        oOrder.nClearAllPriceType = 2  # limit price
        oOrder.bstrClearAllOrderPrice = str(sig.entry_price)

        try:
            bstrMessage, nCode = self.m_pSKOrder.SendStockStrategyDayTrade(
                self.user_id, False, oOrder)
        except Exception as e:
            err_str = str(e)
            if '924' in err_str or '不支持' in err_str or 'not support' in err_str.lower():
                self.log.warning(f"  {sig.symbol}: Does not support day trade, SKIP")
            else:
                self.log.error(f"  {sig.symbol}: Smart Trade exception - {e}")
            sig.state = PositionState.CANCELLED
            return

        if nCode == 0:
            sig.order_seq = bstrMessage
            sig.state = PositionState.FILLED
            self.active_positions[sig.symbol] = sig
            self.log.info(
                f"  SMART ORDER: {sig.symbol} {sig.direction.value} {sig.shares} shares "
                f"@ {sig.entry_price} [{sig.tier}] "
                f"SL={self.config.stop_loss_pct*100:.0f}% TP={getattr(sig, '_tp_pct', self.config.take_profit_pct)*100:.0f}% "
                f"ForceClose=13:25")
        else:
            msg = self.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
            self.log.error(f"  {sig.symbol}: order failed - {msg} ({bstrMessage})")
            sig.state = PositionState.CANCELLED

    # ----------------------------------------------------------
    # STEP 3: REAL-TIME MONITORING
    # ----------------------------------------------------------

    def monitor_positions(self):
        """Monitor: wait for Smart Trade completion."""
        self.log.info("=" * 60)
        self.log.info("STEP 3: Waiting for Smart Trade completion...")
        self.log.info("  SL/TP/ForceClose handled by exchange (Smart Trade)")
        self.log.info(f"  Expected completion by {self.config.force_exit_time}")

        force_exit_dt = self._parse_time(self.config.force_exit_time)
        # Add 5 min buffer after force close time for settlement
        end_dt = force_exit_dt.replace(minute=force_exit_dt.minute + 5)

        while self.running:
            now = datetime.now()
            if now >= end_dt:
                self.log.info("  All orders should be completed.")
                break

            # Check if all positions are resolved (for reporting)
            active_count = sum(
                1 for sig in self.active_positions.values()
                if sig.state in (PositionState.FILLED, PositionState.MONITORING))

            if active_count == 0:
                self.log.info("  All positions resolved.")
                break

            # Update prices for reporting (every 60s, lightweight)
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
                        sig = self.active_positions[sym]
                        # Detect likely exit for reporting
                        if sig.direction == Direction.SHORT:
                            if price >= sig.sl_price:
                                self._mark_exit(sig, price, "STOP_LOSS")
                            elif price <= sig.tp_price:
                                self._mark_exit(sig, price, "TAKE_PROFIT")
                        else:
                            if price <= sig.sl_price:
                                self._mark_exit(sig, price, "STOP_LOSS")
                            elif price >= sig.tp_price:
                                self._mark_exit(sig, price, "TAKE_PROFIT")

            time.sleep(5)

        # Final force close check
        self._force_close_all()

    def _mark_exit(self, sig: Signal, price: float, reason: str):
        """Mark a position as exited for reporting (exchange already executed it)"""
        if sig.direction == Direction.SHORT:
            sig.pnl = (sig.entry_price - price) * sig.shares
        else:
            sig.pnl = (price - sig.entry_price) * sig.shares
        sig.pnl -= (sig.entry_price + price) * sig.shares * self.config.cost_per_trade
        sig.exit_price = price
        sig.exit_reason = reason
        sig.state = PositionState.EXITED

        self.log.info(
            f"  EXITED: {sig.symbol} {sig.direction.value} @ {price} "
            f"[{reason}] PnL={sig.pnl:+,.0f}")

        self.closed_trades.append({
            "time": datetime.now().isoformat(),
            "symbol": sig.symbol, "name": sig.name,
            "direction": sig.direction.value, "tier": sig.tier,
            "shares": sig.shares, "entry": sig.entry_price,
            "exit": price, "reason": reason, "pnl": sig.pnl,
        })
        del self.active_positions[sig.symbol]

    def _close_position(self, sig: Signal, price: float, reason: str):
        """Auto-close position"""
        if sig.direction == Direction.SHORT:
            # 買回平空
            buy_sell = 0  # Buy
            flag = 2      # 融券
        else:
            # 賣出平多
            buy_sell = 1  # Sell
            flag = 0      # 現股

        bstrMessage, nCode = self.send_order(
            stock_no=sig.symbol,
            buy_sell=buy_sell,
            flag=flag,
            price=price,
            qty=sig.shares,
            trade_type=0,
        )

        if nCode == 0:
            sig.exit_price = price
            sig.exit_reason = reason
            sig.state = PositionState.EXITED

            # Calculate PnL
            if sig.direction == Direction.SHORT:
                sig.pnl = (sig.entry_price - price) * sig.shares
            else:
                sig.pnl = (price - sig.entry_price) * sig.shares
            sig.pnl -= (sig.entry_price + price) * sig.shares * self.config.cost_per_trade

            self.log.info(
                f"  EXIT: {sig.symbol} {sig.direction.value} @ {price} "
                f"[{reason}] PnL={sig.pnl:+,.0f}")

            self.closed_trades.append({
                "time": datetime.now().isoformat(),
                "symbol": sig.symbol, "name": sig.name,
                "direction": sig.direction.value, "tier": sig.tier,
                "shares": sig.shares, "entry": sig.entry_price,
                "exit": price, "reason": reason, "pnl": sig.pnl,
            })
            del self.active_positions[sig.symbol]
        else:
            msg = self.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
            self.log.error(f"  {sig.symbol}: close failed - {msg}")

    def _force_close_all(self):
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
            self._mark_exit(sig, price, "FORCE_CLOSE")

    # ----------------------------------------------------------
    # STEP 4: REPORT
    # ----------------------------------------------------------

    def daily_report(self):
        """Daily settlement report"""
        self.log.info("=" * 60)
        self.log.info("DAILY REPORT")

        if not self.closed_trades:
            self.log.info("  No trades today.")
            return

        df = pd.DataFrame(self.closed_trades)
        total_pnl = df["pnl"].sum()
        wins = (df["pnl"] > 0).sum()
        total = len(df)

        self.log.info(f"  Trades: {total}")
        self.log.info(f"  Win rate: {wins}/{total} ({wins/total*100:.1f}%)")
        self.log.info(f"  Total PnL: {total_pnl:+,.0f}")
        self.log.info(f"  Avg PnL: {total_pnl/total:+,.0f}")

        today = datetime.now().strftime("%Y-%m-%d")
        csv_path = self.config.log_dir / f"trades_{today}.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        self.log.info(f"  Saved: {csv_path}")

    # ----------------------------------------------------------
    # MAIN LOOP
    # ----------------------------------------------------------

    def run(self):
        """Main execution flow"""
        self.running = True
        self.log.info("=" * 60)
        self.log.info("GAP FADE v3 AUTO TRADER (Capital SKCOM)")
        self.log.info(f"Capital: {self.config.capital:,.0f}")
        self.log.info(f"Mode: FULLY AUTOMATIC")
        self.log.info(f"Time: {datetime.now().isoformat()}")

        try:
            self.connect()
            self._wait_until("09:00")
            self._wait_for_quotes(min_stocks=200, timeout_sec=10)
            self.scan_signals()

            if not self.signals:
                self.log.info("No signals. Done.")
                return

            # Enter immediately at open (no confirmation wait)
            self.confirm_and_enter()

            if not self.active_positions:
                self.log.info("No positions entered. Done.")
                return

            self.monitor_positions()
            self.daily_report()

        except KeyboardInterrupt:
            self.log.info("Interrupted by user.")
            self._force_close_all()
        except Exception as e:
            self.log.error(f"FATAL: {e}", exc_info=True)
            self._force_close_all()
        finally:
            self.running = False
            self.disconnect()

    def _wait_until(self, time_str: str):
        """Wait until specified time"""
        target = self._parse_time(time_str)
        now = datetime.now()
        if now >= target:
            return
        wait_sec = (target - now).total_seconds()
        self.log.info(f"  Waiting {wait_sec:.0f}s until {time_str}...")
        while datetime.now() < target:
            remaining = (target - datetime.now()).total_seconds()
            time.sleep(min(10, max(1, remaining)))

    def _wait_for_quotes(self, min_stocks: int = 200, timeout_sec: int = 10):
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
    def _parse_time(time_str: str) -> datetime:
        today = datetime.now().date()
        h, m = map(int, time_str.split(":"))
        return datetime(today.year, today.month, today.day, h, m)


# ============================================================
# SIMULATION MODE (paper trading, no real orders)
# ============================================================

class GapFadeSimulator(GapFadeAutoTrader):
    """Paper trading: no real orders, uses Yahoo for quotes"""

    def connect(self):
        self.log.info("SIMULATION MODE - No real orders")
        self.yahoo.connect()

    def disconnect(self):
        pass

    def _fetch_market_history(self):
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

    def _compute_stock_features(self, signals):
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

    def _calc_position_score(self, sig) -> float:
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

        # Store raw score for TP calculation
        sig._score = score

        # === MAP SCORE TO POSITION ===
        if score >= 10: return 0.12
        elif score >= 7: return 0.09
        elif score >= 5: return 0.07
        elif score >= 3: return 0.05
        elif score >= 1: return 0.04
        else: return 0.02

    def _place_entry_order(self, sig: Signal):
        sig.state = PositionState.FILLED
        sig.fill_price = sig.entry_price
        self.active_positions[sig.symbol] = sig
        self.log.info(
            f"  [SIM] ENTER: {sig.symbol} {sig.direction.value} "
            f"{sig.shares} shares @ {sig.entry_price} [{sig.tier}]")

    def send_order(self, *args, **kwargs):
        return ("SIM_OK", 0)

    def _close_sim(self, sig, price, reason):
        if sig.direction == Direction.SHORT:
            sig.pnl = (sig.entry_price - price) * sig.shares
        else:
            sig.pnl = (price - sig.entry_price) * sig.shares
        sig.pnl -= (sig.entry_price + price) * sig.shares * self.config.cost_per_trade
        sig.exit_price = price
        sig.exit_reason = reason
        sig.state = PositionState.EXITED
        self.log.info(
            f"  [SIM] EXIT: {sig.symbol} {sig.direction.value} @ {price} "
            f"[{reason}] PnL={sig.pnl:+,.0f}")
        self.closed_trades.append({
            "time": datetime.now().isoformat(),
            "symbol": sig.symbol, "name": sig.name,
            "direction": sig.direction.value, "tier": sig.tier,
            "shares": sig.shares, "entry": sig.entry_price,
            "exit": price, "reason": reason, "pnl": sig.pnl,
        })
        del self.active_positions[sig.symbol]

    def _force_close_all_sim(self, client):
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
            self._close_sim(sig, price, "FORCE_CLOSE")



# ============================================================
# ENTRY POINT
# ============================================================

class GapFadeNowTrader(GapFadeSimulator):
    """Immediate execution: skip time waits, run logic right now"""

    def run(self):
        self.running = True
        self.log.info("=" * 60)
        self.log.info("GAP FADE v3 NOW MODE (immediate, no time wait)")
        self.log.info(f"Capital: {self.config.capital:,.0f}")
        self.log.info(f"Time: {datetime.now().isoformat()}")

        try:
            self.connect()

            # Fetch market history for position scoring
            self._fetch_market_history()
            # Scan immediately
            self.scan_signals()

            if not self.signals:
                self.log.info("No signals right now. Done.")
                return

            # Enter immediately
            self.log.info("  [NOW] Entering at open price...")
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
        self._force_close_all_sim(None)


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

    trader.run()
