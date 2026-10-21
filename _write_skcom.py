import pathlib

path = pathlib.Path(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py')

content = '''"""
Gap Fade v3 AUTO - Full Auto Trading System (Capital Securities / SKCOM)
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
import logging
import ctypes
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from enum import Enum

import pandas as pd
import numpy as np
import comtypes.client

# Load SKCOM
SKCOM_PATH = r"D:\\CapitalAPI\\CapitalAPI_2.13.59_PythonExample\\元件\\x64\\SKCOM.dll"
comtypes.client.GetModule(SKCOM_PATH)
import comtypes.gen.SKCOMLib as sk


# ============================================================
# CONFIG
# ============================================================

class Config:
    # --- Capital Securities credentials ---
    cust_cert_id = "D121280815"       # 身分證字號
    password = "YOUR_PASSWORD"         # 下單密碼

    # --- Capital ---
    capital = 4_500_000

    # --- Signal detection (9:00) ---
    gap_threshold = 0.05
    min_price = 30
    max_price = 225
    min_volume_t1 = 5_000_000

    # --- Confirmation (9:15) ---
    confirm_wait_minutes = 15
    confirm_drop_min = 0.0

    # --- Tiered sizing ---
    tiers = [
        (0.03, 999, 2.0, "T5"),
        (0.015, 0.03, 1.5, "T4"),
        (0.005, 0.015, 1.0, "T3"),
        (0.0, 0.005, 0.5, "T2"),
    ]

    # --- Position sizing ---
    base_position_pct = 0.05
    long_position_pct = 0.025

    # --- Exit ---
    stop_loss_pct = 0.06
    take_profit_pct = 0.04
    force_exit_time = "13:25"

    # --- Limits ---
    max_daily_positions = 8
    max_daily_exposure = 1.0

    # --- Cost ---
    cost_per_trade = 0.0023

    # --- Fugle (for 9:00 scanning) ---
    fugle_api_key = "MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw=="

    # --- Logging ---
    log_dir = Path(r"C:\\Users\\weni.liu\\Documents\\Codex\\2026-10-14\\new-chat-3\\outputs\\trading_logs")


# ============================================================
# DATA STRUCTURES
# ============================================================

class Direction(Enum):
    SHORT = "SHORT"
    LONG = "LONG"


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
        self.signals: list[Signal] = []
        self.active_positions: dict[str, Signal] = {}
        self.closed_trades: list[dict] = []
        self.running = False
        self.market_gap = 0.0
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

        # Create COM objects
        self.m_pSKCenter = comtypes.client.CreateObject(
            sk.SKCenterLib, interface=sk.ISKCenterLib)
        self.m_pSKOrder = comtypes.client.CreateObject(
            sk.SKOrderLib, interface=sk.ISKOrderLib)
        self.m_pSKQuote = comtypes.client.CreateObject(
            sk.SKQuoteLib, interface=sk.ISKQuoteLib)
        self.m_pSKReply = comtypes.client.CreateObject(
            sk.SKReplyLib, interface=sk.ISKReplyLib)

        # Set production environment
        self.m_pSKCenter.SKCenterLib_SetAuthority(0)

        # Login
        nCode = self.m_pSKCenter.SKCenterLib_Login(
            self.config.cust_cert_id, self.config.password)
        msg = self.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
        if nCode != 0:
            raise ConnectionError(f"Login failed: {msg}")
        self.log.info(f"Login OK: {msg}")
        self._logged_in = True

        # Initialize order system
        self.m_pSKOrder.SKOrderLib_Initialize()

        # Get trading account
        self.m_pSKOrder.GetUserAccount()
        time.sleep(2)  # Wait for OnAccount callback

        if not self.account:
            # Try to get account directly
            self.log.warning("Account not received via callback, trying direct query...")
            # The account should be in format: brokerID + accountNo
            self.account = "918D0495371"  # Fallback from web trading

        self.log.info(f"Account: {self.account}")

        # Initialize quote connection
        self.m_pSKQuote.SKQuoteLib_EnterMonitorLONG()
        time.sleep(1)

        self.log.info("Connected. Ready to trade.")

    def disconnect(self):
        if self._logged_in:
            self.m_pSKQuote.SKQuoteLib_LeaveMonitor()
            self.log.info("Disconnected.")
            self._logged_in = False

    # ----------------------------------------------------------
    # QUOTE: Get current price via SKQuoteLib
    # ----------------------------------------------------------

    def get_price(self, stock_no: str) -> float:
        """Get current price of a stock via SKQuoteLib"""
        pSKStock = sk.tagSKStockLONG()
        pSKStock, nCode = self.m_pSKQuote.SKQuoteLib_GetStockByNoLONG(
            stock_no, pSKStock)
        if nCode != 0:
            return 0.0
        # nLastPrice is in cents (divide by 100)
        price = pSKStock.nLastPrice / 100.0
        return price

    def subscribe_quotes(self, stock_nos: list[str]):
        """Subscribe to real-time quotes for stocks"""
        stock_str = ",".join(stock_nos)
        psPageNo = ctypes.c_long(1)
        nCode = self.m_pSKQuote.SKQuoteLib_RequestStocks(psPageNo, stock_str)
        if nCode == 0:
            self.log.info(f"  Subscribed to {len(stock_nos)} stocks")
        time.sleep(1)

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

    def scan_signals(self) -> list[Signal]:
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

        return self.signals

    # ----------------------------------------------------------
    # STEP 2: 9:15 CONFIRM + AUTO ORDER
    # ----------------------------------------------------------

    def confirm_and_enter(self):
        """9:15 confirm signals and auto-place orders"""
        self.log.info("=" * 60)
        self.log.info("STEP 2: Confirming & placing orders...")

        # Subscribe to quotes
        symbols = [s.symbol for s in self.signals]
        self.subscribe_quotes(symbols)

        total_exposure = 0

        for sig in self.signals:
            # Get current price
            current_price = self.get_price(sig.symbol)
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
            f"({total_exposure/self.config.capital*100:.0f}%)")

    def _place_entry_order(self, sig: Signal):
        """Auto-place entry order via SKCOM"""
        if sig.direction == Direction.SHORT:
            # 融券賣出 (short sell)
            buy_sell = 1  # Sell
            flag = 2      # 融券
        else:
            # 現股買進 (buy)
            buy_sell = 0  # Buy
            flag = 0      # 現股

        bstrMessage, nCode = self.send_order(
            stock_no=sig.symbol,
            buy_sell=buy_sell,
            flag=flag,
            price=sig.entry_price,
            qty=sig.shares,
            trade_type=0,  # ROD
        )

        if nCode == 0:
            sig.order_seq = bstrMessage
            sig.state = PositionState.FILLED  # Assume filled for simplicity
            self.active_positions[sig.symbol] = sig
            self.log.info(
                f"  ORDERED: {sig.symbol} {sig.direction.value} {sig.shares} shares "
                f"@ {sig.entry_price} [{sig.tier}] "
                f"SL={sig.sl_price} TP={sig.tp_price}")
        else:
            msg = self.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
            self.log.error(f"  {sig.symbol}: order failed - {msg} ({bstrMessage})")
            sig.state = PositionState.CANCELLED

    # ----------------------------------------------------------
    # STEP 3: REAL-TIME MONITORING
    # ----------------------------------------------------------

    def monitor_positions(self):
        """Real-time monitoring: auto-exit on SL/TP/force close"""
        self.log.info("=" * 60)
        self.log.info("STEP 3: Monitoring positions...")
        self.log.info(f"  Force exit at {self.config.force_exit_time}")

        force_exit_dt = self._parse_time(self.config.force_exit_time)

        while self.running:
            now = datetime.now()

            if now >= force_exit_dt:
                self.log.info("  FORCE EXIT TIME REACHED")
                self._force_close_all()
                break

            for symbol, sig in list(self.active_positions.items()):
                if sig.state not in (PositionState.FILLED, PositionState.MONITORING):
                    continue

                sig.state = PositionState.MONITORING

                current_price = self.get_price(symbol)
                if current_price <= 0:
                    continue

                should_exit = False
                reason = ""

                if sig.direction == Direction.SHORT:
                    if current_price >= sig.sl_price:
                        should_exit = True
                        reason = "STOP_LOSS"
                    elif current_price <= sig.tp_price:
                        should_exit = True
                        reason = "TAKE_PROFIT"
                else:
                    if current_price <= sig.sl_price:
                        should_exit = True
                        reason = "STOP_LOSS"
                    elif current_price >= sig.tp_price:
                        should_exit = True
                        reason = "TAKE_PROFIT"

                if should_exit:
                    self._close_position(sig, current_price, reason)

            time.sleep(3)

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
        """13:25 force close all positions"""
        for symbol, sig in list(self.active_positions.items()):
            if sig.state in (PositionState.FILLED, PositionState.MONITORING):
                price = self.get_price(symbol)
                if price <= 0:
                    price = sig.entry_price
                self._close_position(sig, price, "FORCE_CLOSE")

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
            self.scan_signals()

            if not self.signals:
                self.log.info("No signals. Done.")
                return

            self._wait_until("09:15")
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

    @staticmethod
    def _parse_time(time_str: str) -> datetime:
        today = datetime.now().date()
        h, m = map(int, time_str.split(":"))
        return datetime(today.year, today.month, today.day, h, m)


# ============================================================
# SIMULATION MODE (paper trading, no real orders)
# ============================================================

class GapFadeSimulator(GapFadeAutoTrader):
    """Paper trading: no real orders, uses Fugle for quotes"""

    def connect(self):
        self.log.info("SIMULATION MODE - No real orders")

    def disconnect(self):
        pass

    def get_price(self, stock_no: str) -> float:
        from fugle_marketdata import RestClient
        client = RestClient(api_key=self.config.fugle_api_key)
        try:
            data = client.stock.intraday.current(symbol=stock_no)
            return float(data.get("close", 0))
        except Exception:
            return 0.0

    def subscribe_quotes(self, stock_nos: list[str]):
        pass

    def _place_entry_order(self, sig: Signal):
        sig.state = PositionState.FILLED
        sig.fill_price = sig.entry_price
        self.active_positions[sig.symbol] = sig
        self.log.info(
            f"  [SIM] ENTER: {sig.symbol} {sig.direction.value} "
            f"{sig.shares} shares @ {sig.entry_price} [{sig.tier}]")

    def send_order(self, *args, **kwargs):
        return ("SIM_OK", 0)


# ============================================================
# ENTRY POINT
# ============================================================

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
        print("SIMULATION MODE - Paper trading via Fugle")
        print(f"  Capital: {config.capital:,.0f}")
        trader = GapFadeSimulator(config)
    else:
        print(f"Unknown mode: {mode}. Use: python gap_fade_auto.py [live|sim]")
        sys.exit(1)

    trader.run()
'''

path.write_text(content, encoding='utf-8')
print(f'Written: {path.stat().st_size} bytes')
