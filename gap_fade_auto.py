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
# Everything this script reads/writes lives next to the script itself, so moving the
# folder does not silently break live or paper mode.
_HERE = Path(__file__).resolve().parent


# ============================================================
# CONFIG
# ============================================================


DISPOSAL_PANEL = r"D:\gapfade_data\disposal_panel_full.pkl"


# --- Day-trade restriction sources -----------------------------------------
#
# Primary: finlab (VIP). Checked against the exchange announcement pages on
# 2026-10-26:
#   * disposal_information covers BOTH markets - 624 of its 2,255 disposal
#     codes are 上櫃. The dataset this file used before,
#     etl:disposal_stock_filter, is 上市 only, and 上櫃 is where ~43 pct of the
#     model's signals come from.
#   * It is a strict superset of the live exchange pages: 0 codes missing, 5
#     extra (2221/3055/3230/3597/4979 - all 處置 10/19~10/27 that the
#     announcement query window missed).
#   * day_trade_short_suspension likewise covers more than TWSE openapi
#     TWTBAU1.
# Warm fetch measured 0.69s + 0.01s, safe at 08:58. finlab republishes
# disposal_information at 08:10 Mon-Sat, i.e. before the open.
#
# Fallbacks, used only if finlab does not answer: the exchange announcement
# pages directly, then the historical panel. Every degraded path logs loudly -
# the old code dropped silently onto a 上市-only list, which is the worst kind
# of failure because it looks like it worked.
FINLAB_TOKEN = "Vww04G2yj5qcHkqX6yNCKIOw/GE2oJ9dIlFftXoeN3NqjQTv0YAqWujox5k/ilKd#vip_m"
FINLAB_DISPOSAL_KEY = "disposal_information"
FINLAB_NO_DAYTRADE_KEY = "day_trade_short_suspension"
# 處置 is announced the evening before it takes effect, so a healthy feed is at
# most 1 day behind. 5 is a generous tripwire, not a normal condition.
FINLAB_STALE_WARN_DAYS = 5

DISPOSAL_PANEL = r"D:\gapfade_data\disposal_panel_full.pkl"

TWSE_PUNISH_URL = "https://www.twse.com.tw/announcement/punish"
TPEX_DISPOSAL_URL = "https://www.tpex.org.tw/www/zh-tw/bulletin/disposal"
TWSE_NO_DAYTRADE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/TWTBAU1"
RESTRICT_LOOKBACK_DAYS = 45   # disposal windows run 5-7 trading days

_common_stock = lambda c: len(c) == 4 and c[0].isdigit()


def _log():
    import logging
    return logging.getLogger("GapFade")


def _roc_date(text):
    """'115/10/20' -> date(2026, 10, 20). None if unparseable."""
    from datetime import date as _date
    parts = (text or "").strip().split("/")
    if len(parts) != 3:
        return None
    try:
        y, m, d = (int(p.strip()) for p in parts)
    except ValueError:
        return None
    if y < 200:                    # ROC year
        y += 1911
    try:
        return _date(y, m, d)
    except ValueError:
        return None


def _roc_compact(text):
    """'1151103' -> date(2026, 11, 3). None if unparseable."""
    from datetime import date as _date
    s = str(text or "").strip()
    if len(s) != 7 or not s.isdigit():
        return None
    try:
        return _date(int(s[:3]) + 1911, int(s[3:5]), int(s[5:7]))
    except ValueError:
        return None


def _window_covers_today(text, today) -> bool:
    """True if a published disposal window contains today.

    Both exchanges publish the resolved calendar window directly: TWSE writes
    '115/10/20～115/10/27' (full-width tilde), TPEx writes '115/10/23~115/11/03'
    (half-width). The 營業日 arithmetic is already resolved by the exchange, so a
    plain containment test reproduces exactly what was announced.
    """
    s = (text or "").replace("～", "~").replace("至", "~")
    parts = [p for p in s.split("~") if p.strip()]
    if len(parts) < 2:
        return False
    d0, d1 = _roc_date(parts[0]), _roc_date(parts[-1])
    if d0 is None or d1 is None:
        return False
    return d0 <= today <= d1


def _col(fields, *needles):
    for idx, f in enumerate(fields or []):
        s = str(f)
        if all(n in s for n in needles):
            return idx
    return None


_finlab_logged_in = False


def _ensure_finlab_login() -> bool:
    global _finlab_logged_in
    if _finlab_logged_in:
        return True
    log = _log()
    try:
        import warnings
        import finlab
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            finlab.login(FINLAB_TOKEN)
        _finlab_logged_in = True
        return True
    except Exception as exc:
        log.warning(f"  finlab login failed: {type(exc).__name__}: {exc}")
        return False


def _from_finlab(today) -> set:
    """處置 + 暫停先賣後買當沖, both markets. Empty set means no answer."""
    log = _log()
    restricted = set()
    try:
        import time as _t
        import pandas as _pd
        from finlab import data as fdata
        if not _ensure_finlab_login():
            return set()
        t0 = _t.time()
        now = _pd.Timestamp(today)

        di = fdata.get(FINLAB_DISPOSAL_KEY)
        di["symbol"] = di["symbol"].astype(str).str.zfill(4)
        live = di.loc[(
            _pd.to_datetime(di["處置開始時間"]) <= now) & (
            _pd.to_datetime(di["處置結束時間"]) >= now), "symbol"]
        disposal = {c for c in live if _common_stock(c)}
        restricted |= disposal

        # Freshness. 處置 is published the evening before it starts, so anything
        # more than a few days behind means today's announcements are absent.
        pub = _pd.to_datetime(di["date"]).max()
        lag = (now - pub).days
        if lag > FINLAB_STALE_WARN_DAYS:
            log.warning(
                f"  FINLAB DISPOSAL STALE: newest 處置 announcement is "
                f"{pub.date()}, {lag} days behind {today}. Stocks disposed "
                f"after that date will NOT be excluded and the broker will "
                f"reject them at 09:00.")

        dt = fdata.get(FINLAB_NO_DAYTRADE_KEY)
        dt["symbol"] = dt["symbol"].astype(str).str.zfill(4)
        live2 = dt.loc[(
            _pd.to_datetime(dt["停止先賣後買開始日"]) <= now) & (
            _pd.to_datetime(dt["停止先賣後買結束日"]) >= now), "symbol"]
        no_dt = {c for c in live2 if _common_stock(c)}
        restricted |= no_dt

        log.info(f"  Restricted from finlab in {_t.time()-t0:.2f}s: "
                 f"{len(disposal)} 處置 (both markets), "
                 f"{len(no_dt)} 暫停先賣後買當沖")
        return restricted
    except Exception as exc:
        log.warning(f"  finlab restriction source failed: "
                    f"{type(exc).__name__}: {exc}")
        return set()


def _from_exchanges(today) -> set:
    """Live announcement pages. Union of both markets + 暫停先賣後買當沖."""
    log = _log()
    from datetime import timedelta as _td
    import requests
    restricted = set()
    since = today - _td(days=RESTRICT_LOOKBACK_DAYS)

    def fetch(url, params=None):
        try:
            r = requests.get(url, params=params, timeout=15,
                             headers={"User-Agent": "Mozilla/5.0"})
        except Exception as exc:
            log.warning(f"  restriction source unreachable {url}: "
                        f"{type(exc).__name__}: {exc}")
            return None
        if r.status_code != 200:
            log.warning(f"  restriction source HTTP {r.status_code}: {url}")
            return None
        try:
            return r.json()
        except Exception as exc:
            log.warning(f"  restriction source not JSON: {url} ({exc})")
            return None

    js = fetch(TWSE_PUNISH_URL, {"response": "json",
                                 "startDate": since.strftime("%Y%m%d"),
                                 "endDate": today.strftime("%Y%m%d")})
    if isinstance(js, dict) and js.get("data"):
        f = js.get("fields") or []
        ic, isp = _col(f, "證券代號"), _col(f, "處置", "時間")
        if ic is None or isp is None:
            log.warning(f"  TWSE punish: unexpected fields {f[:10]}")
        else:
            restricted |= {str(r[ic]).strip() for r in js["data"]
                           if len(r) > max(ic, isp)
                           and _window_covers_today(r[isp], today)}

    js = fetch(TPEX_DISPOSAL_URL, {
        "type": "all",
        "startDate": f"{since.year - 1911}/{since.month:02d}/{since.day:02d}",
        "endDate": f"{today.year - 1911}/{today.month:02d}/{today.day:02d}"})
    if isinstance(js, dict) and js.get("tables"):
        for tb in js["tables"]:
            f = tb.get("fields") or []
            ic, isp = _col(f, "證券代號"), _col(f, "處置", "時間")
            if ic is None or isp is None:
                continue
            restricted |= {str(r[ic]).strip() for r in tb.get("data") or []
                           if len(r) > max(ic, isp)
                           and _window_covers_today(r[isp], today)}

    js = fetch(TWSE_NO_DAYTRADE_URL)
    if isinstance(js, list):
        for row in js:
            if not isinstance(row, dict):
                continue
            code = str(row.get("Code", "")).strip()
            d0 = _roc_compact(row.get("StartDate"))
            d1 = _roc_compact(row.get("EndDate"))
            if code and d0 and d1 and d0 <= today <= d1:
                restricted.add(code)

    restricted = {c for c in restricted if _common_stock(c)}
    if restricted:
        log.warning("  Restricted list came from the exchange announcement "
                    "pages, NOT finlab. Measured 2026-10-26 this path misses "
                    "5 of the 14 active 處置 stocks.")
    return restricted


def _from_panel(today) -> set:
    """Historical panel. Last resort, and loud about how stale it is."""
    log = _log()
    try:
        import pandas as _pd
        dp = _pd.read_pickle(DISPOSAL_PANEL)
        dp["date"] = _pd.to_datetime(dp["date"])
        dp["stock"] = dp["stock"].astype(str).str.zfill(4)
        last = dp["date"].max()
        lag = (_pd.Timestamp(today) - last).days
        if lag > 0:
            log.warning(
                f"  DISPOSAL PANEL STALE: newest row {last.date()} is {lag} "
                f"days behind {today}. It cannot describe today's 處置 list.")
        hit = dp.loc[dp["date"] == _pd.Timestamp(today), "stock"]
        return {c for c in hit if _common_stock(c)}
    except FileNotFoundError:
        log.warning(f"  DISPOSAL PANEL MISSING: {DISPOSAL_PANEL}")
    except Exception as exc:
        log.warning(f"  DISPOSAL PANEL UNREADABLE: {type(exc).__name__}: {exc}")
    return set()


def get_restricted_stocks() -> set:
    """Codes that cannot be day-traded today (處置 + 暫停先賣後買當沖).

    Sources in priority order; the first that answers wins:
      1. finlab disposal_information + day_trade_short_suspension - both
         markets, refreshed 08:10, superset of everything else.
      2. Exchange announcement pages (TWSE + TPEx + TWTBAU1) - reachable
         without a key, but measured to miss ~1/3 of active 處置 stocks.
      3. disposal_panel_full.pkl - historical only, useless for today unless
         refreshed.

    A missed restricted stock is an order the broker rejects at 09:00; an
    over-excluded stock costs one signal. The first is far more expensive, so
    every fallback path logs loudly instead of returning a quietly shorter list.
    """
    from datetime import date as _date
    log = _log()
    today = _date.today()

    restricted = _from_finlab(today)
    if not restricted:
        restricted = _from_exchanges(today)
    if not restricted:
        restricted = _from_panel(today)
    source_ok = bool(restricted)

    # Always exclude known non-day-trade stocks
    restricted.update(["2330", "2317"])

    if source_ok:
        log.info(f"  Restricted (cannot day-trade): {len(restricted)} codes")
    else:
        log.warning(
            f"  NO RESTRICTION SOURCE ANSWERED for {today}. Only the "
            f"{len(restricted)} hardcoded codes are excluded - disposal stocks "
            f"will reach the exchange and be rejected there.")
    return restricted


def get_borrowable_stocks() -> tuple:
    """Codes that can actually be shorted today = lending quota > 0 in the most
    recent published session (T-1).

    Source: finlab `security_lending_sell:借券賣出限額` (TWSE 借券賣出限額, published
    21:26-23:26 the night before, so the T-1 row is the newest one at 09:00 and
    using it is not look-ahead).

    Measured 2026-10-27 against the exchange's own announcement
    `sellable_lending_quota:可借券賣出股數` over the 92 days where both exist:
    T-1 quota vs same-day announcement agree 100.00% (2 disagreements / 195,500).
    The previous source `etl:lending_fee_volume` only says a stock has been
    borrowed at some point since 2015 - it cannot answer "is there stock today".

    Returns (codes, as_of_date) or (None, reason).
    """
    if not _ensure_finlab_login():
        return None, "finlab login unavailable"
    try:
        from finlab import data as fdata
        q = pd.DataFrame(fdata.get('security_lending_sell:借券賣出限額'))
        if len(q) == 0:
            return None, "empty lending quota panel"
        row = q.iloc[-1]
        return {str(c) for c in row[row > 0].index}, str(pd.Timestamp(q.index[-1]).date())
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"[:120]



class Config:
    # --- Capital Securities credentials ---
    cust_cert_id = "D121280815"       # 身分證字號
    password = "Zaq582811@"         # 下單密碼

    # --- Capital ---
    capital = 4_500_000

    # ===== v13 SIGNAL (9:00, market-adjusted opening gap) =====
    gap_short_min = 0.015           # SHORT: adj_gap >= +1.5 pct
    gap_long_min = 0.05             # LONG:  adj_gap <= -5.0 pct
    min_price = 30                  # prev_close >= 30 TWD
    # T-1 turnover floor is NOT a fixed amount: it is derived from current
    # equity via min_turnover_factor (see _min_turnover_floor) so the
    # participation rate stays 5 pct at any capital size.
    benchmark_no = "0050"           # opening-gap benchmark, observable at 09:00

    # ===== v13 MODEL (exported by v13_export_model.py) =====
    model_path = _HERE / "v13_model.pkl"
    pred_q_min = 0.20               # skip bottom 20 pct of predicted PnL
    max_factor_lag_days = 10      # panel older than this -> feed NaN factors, like the backtest

    # ===== v13 EXIT =====
    stop_loss_pct = 0.04            # SL 4 pct, capped by price limit (dynamic)
    take_profit_pct = 0.12          # TP low
    take_profit_high_pct = 0.20     # TP high when q1 >= q1_tp_threshold
    q1_tp_threshold = 0.85
    force_exit_time = "13:25"

    # ===== v13 POSITION SIZING (pred_q ladder x regime multipliers) =====
    position_multiplier = 1.0       # leverage knob (backtest frontier: 0.6/1.0/1.5)
    pos_cap_pct = 0.25              # hard cap per name
    max_total_exposure = 1.00       # ZERO MARGIN: total notional <= equity
    zt_bp1 = 0.015; zt_m1 = 10.0   # zt_dist < 1.5 pct  -> x10 (loss capped by limit-up)
    zt_bp2 = 0.045; zt_m2 = 2.5    # zt_dist < 4.5 pct  -> x2.5
    dd_th1 = 0.006; dd_scale1 = 0.30   # equity DD > 0.6 pct  -> x0.30
    dd_th2 = 0.012; dd_scale2 = 0.12   # equity DD > 1.2 pct  -> x0.12
    k_model_scale = 0.02            # k_model = clip(0.5 + pred/0.02, 0, 2)
    # k_model is OFF by default. Measured on the corrected universe (2026-10-27):
    # it adds no return (CAGR 167.8% vs 167.3%) and worsens MDD (-4.34% vs -4.59%),
    # and because it scales with the RAW magnitude of pred it is the single biggest
    # source of run-to-run instability - a 0.28% change in the training pool moved
    # the reported CAGR by ~16pp. k_trail stays ON: removing it costs 73pp of CAGR
    # and takes MDD from -4.3% to -12.8%.
    use_k_model = False
    # Skip designs too small to buy a whole lot. At 4,500,000 TWD a 0.4% design
    # weight is 18,000 TWD, which cannot be bought for any stock above 18 TWD, so
    # those rows only inflate the intended trade count. Dropping them raises the
    # realised share of the design from 60% to 70% and improves Calmar (49.7->50.8).
    min_pos_pct = 0.005
    # --- R6 sizing rules (v13_sizing_lab.py, measured 2026-10-27) ---
    # Design weight -> floor to whole lots, but first (a) skip names whose 1-lot
    # value exceeds 250,000 TWD (share price > 250): at 4.5M the lot granularity on
    # high-priced names is far coarser than the model weight, and (b) cap a single
    # trade at 1,000,000 TWD - uncapped it reaches 2,090,000 (47 pct of equity).
    # Measured: CAGR 155.4 pct / MDD -3.6 pct / Calmar 43.2, vs floor-only
    # 165.7 / -4.2 / 39.8. Lower CAGR, strictly better risk.
    max_per_trade_pct = 0.25  # dynamic: 25% of current equity (scales with compounding)
    max_lot_value_pct = 0.25  # dynamic: skip if 1 lot > 25% of equity (scales with capital)
    # Minimum T-1 turnover: dynamic, maintains 5% participation rate.
    # Formula: min_turnover = 5 x equity (= max_position / 5%)
    # At 4.5M: 2250萬 | At 10M: 5000萬 | At 20M: 1億
    # Participation rate always <= 5% one-way, <= 10% round-trip (day trade).
    min_turnover_factor = 5.0  # min_turnover = factor x equity
    # Operational safety net only, NOT a performance rule. There is no count limit in the
    # strategy: capital (zero margin) is the gate. Measured on 2014-2026 (count_cap.py):
    # 34 candidates/day pass the filters, 9.4 get funded, p99 = 22, max = 26. 30 therefore
    # never binds on performance; it only bounds API load and order races on freak days
    # (up to 545 candidates in one day).
    max_orders_per_day = 30
    # --- paper mode (see GapFadePaperTrader) ---
    paper_poll_sec = 10         # simulated-fill resolution; 22 names batch in 0.47s
    paper_probe_zhang = 1       # probe order size in ZHANG (nQty is zhang, not shares)
    k_trail_scale = 0.02            # k_trail = clip(0.5 + trail30/0.02, 0.3, 2)
    equity_state_path = _HERE / "equity_state.json"

    # --- Cost ---
    cost_per_trade = 0.00109  # 0.2 pct x1.7 zhe + day-trade tax halved, per side

    # --- Fugle (real-time scanning) ---
    fugle_api_key = "MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw=="
    # Batch endpoint: intraday/quotes?symbol=a,b,c. Measured 2026-10-26: 1,000
    # symbols/request, 3,307 codes (1,532 TWSE + 1,775 TPEx) in 4 requests /
    # 1.5s, 100 pct coverage of BOTH markets. TWSE MIS only answers for 上市.
    fugle_batch_url = "https://api.fugle.tw/marketdata/v1.0/stock/intraday/quotes"
    fugle_batch_size = 1000

    # --- Yahoo Finance (post-market reporting only) ---
    yahoo_batch_size = 50
    yahoo_max_workers = 15
    stock_list_path = _HERE / "valid_stocks.txt"

    # --- Logging ---
    log_dir = _HERE / "trading_logs"


# ============================================================
# DATA STRUCTURES
# ============================================================

class Direction(Enum):
    SHORT = "SHORT"
    LONG = "LONG"


def get_tick_size(price: float) -> float:
    """TWSE/TPEx price increment (买卖间隔 / 涨跌取整间隔) at `price`.

    Measured 2026-10-27 from 2025+ closes of every 4-digit listed/OTC stock in the
    local price store: <10 -> 0.01, 10-50 -> 0.05, 50-100 -> 0.1, 100-500 -> 0.5,
    500-1000 -> 1.0, >=1000 -> 5.0. The 500-1000 and >=1000 bands came back at
    100.0% and 97.8% of observed gaps, so the table is not a guess. The old table
    returned 0.05 under 10 and 10.0 at or above 5000, both wrong.
    """
    if price < 10:
        return 0.01
    elif price < 50:
        return 0.05
    elif price < 100:
        return 0.1
    elif price < 500:
        return 0.5
    elif price < 1000:
        return 1.0
    else:
        return 5.0


def snap_to_valid_price(price: float) -> float:
    """Round `price` to the nearest price the exchange actually accepts.

    The backtest evaluates stops and targets on continuous prices, but an order
    carrying 41.44 in the 10-50 band (increment 0.05) is not a price the market
    has. Measured 2026-10-27 on the 2026-07-23..10-22 4.5M trade list (751 trades):
    89.9% carried such a price. Snapping alone moves total PnL by -1,148 TWD out of
    1,395,438 (-0.08%), worst single trade 2,000 TWD - economically nothing, but the
    order would otherwise be rejected. (An earlier -50,054 TWD reading was not snapping
    at all: it was the lu-tk float artefact below, now fixed in v13_engine/v13_train.)
    """
    tick = get_tick_size(price)
    return round(round(price / tick) * tick, 2)


def calc_price_limits(prev_close: float) -> tuple:
    """Limit-up / limit-down from previous close.

    Two rules, and the second one used to be wrong here:

    1. limit_up rounds DOWN to the increment, limit_down rounds UP.
    2. The increment comes from the band of the LIMIT price, not of the previous
       close. TPEx publishes 次日漲停價, which settles it: 1294 closed 49.50 and its
       limit is 54.40 = floor(54.45/0.1)*0.1 (the 50-100 band), not
       floor(54.45/0.05)*0.05 = 54.45. Same for 1580 (95.80 -> 105.00) and
       1240 (53.70 -> 59.00 up but 48.35 down, i.e. two different bands).

    Verified against TPEx's own published limits for all 867 OTC stocks on
    2026-10-22: this reproduces 99.88% (the old rule got 87.9%). Over
    2007-04..2026-10, 8.15M stock-days, the old rule placed the computed limit
    BELOW the observed intraday high on 9,475 days, which cannot happen; this one
    leaves 922, which are 除權息 reference adjustments and first-day listings.

    This is the bug that kept re-listing locked limit-ups: an open sitting AT the
    true limit compared as "not locked" against an over-high computed limit.
    """
    import math
    raw_up = prev_close * 1.10
    raw_dn = prev_close * 0.90
    tick_up = get_tick_size(raw_up)
    tick_dn = get_tick_size(raw_dn)
    limit_up = math.floor(round(raw_up / tick_up, 9)) * tick_up
    limit_down = math.ceil(round(raw_dn / tick_dn, 9)) * tick_dn
    return round(limit_up, 2), round(limit_down, 2)


def calc_effective_sl(entry: float, prev_close: float, direction,
                      base_sl_pct: float) -> tuple:
    """Dynamic SL: min(normal SL, price_limit - 1 tick). Always reachable."""
    limit_up, limit_down = calc_price_limits(prev_close)
    # The decrement must come from the band of the LIMIT price, because `lu - tick`
    # has to be a price the exchange accepts. 5215 on 2013-01-03: entry 46.70
    # (10-50 band, 0.05), limit 50.10 (50-100 band, 0.1) -> 50.05 is not a valid
    # price there; 50.00 is. 7.3% of SHORT signals and 4.7% of LONG signals straddle
    # a band edge, so this is not hypothetical.
    tick = get_tick_size(limit_up if direction == Direction.SHORT else limit_down)
    # lu - tk is not exact in binary floating point: 43.85 - 0.05 = 43.800000000000004.
    # Compared against a high of 43.80 that reads as "not stopped", which is why the
    # backtest used to miss 165 SHORT stops. Round before comparing and before ordering.

    if direction == Direction.SHORT:
        normal_sl = snap_to_valid_price(entry * (1 + base_sl_pct))
        limit_sl = round(limit_up - tick, 2)
        sl_price = min(normal_sl, limit_sl)
        sl_pct = (sl_price - entry) / entry
    else:
        normal_sl = snap_to_valid_price(entry * (1 - base_sl_pct))
        limit_sl = round(limit_down + tick, 2)
        sl_price = max(normal_sl, limit_sl)
        sl_pct = (entry - sl_price) / entry

    return round(sl_price, 2), max(0.01, sl_pct)


def _to_float(v) -> float:
    """TWSE returns '-' for missing fields."""
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return 0.0


def _parse_smart_key(message: str) -> str:
    """Pull the 條件單號 (smart-order key) out of a SendStockStrategyDayTrade ack.

    The ack looks like: 20261026,預約單已送出, 條件單號：27440222, 交易日:20261027
    The key is what CancelTSStrategyOrderV1 needs, so keep it.
    """
    import re
    m = re.search(r"條件單號[：:]\s*(\d+)", message)
    return m.group(1) if m else ""


def cancel_smart_order(order_lib, user_id: str, account: str, smart_key: str):
    """Cancel one day-trade smart order. nTradeKind 11 = 當沖, nDeleteType 1 = 全部."""
    if not smart_key:
        return -1, "no smart key"
    c = sk.CANCELSTRATEGYORDER()
    c.bstrLogInID = user_id
    c.bstrFullAccount = account
    c.nMarket = 1
    c.bstrParentSmartKey = smart_key
    c.bstrSmartKey = smart_key
    c.nTradeKind = 11
    c.nDeleteType = 1
    c.bstrSeqNo = ""
    c.bstrOrderNo = ""
    c.bstrSmartKeyOut = ""
    c.bstrLongActionKey = ""
    msg, code = order_lib.CancelTSStrategyOrderV1(user_id, c)
    return code, str(msg)



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
    # --- v13 model / execution telemetry ---
    zt_dist: float = 0.0
    prev_turnover: float = 0.0
    pred: float = 0.0
    pred_q: float = 0.0
    q1: float = 0.0
    base_pos: float = 0.0
    submit_ts: float = 0.0
    ack_ts: float = 0.0
    ack_code: int = -999
    ack_msg: str = ""
    smart_key: str = ""




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
        self._replies: list[dict] = []
        self._report_rows: list[dict] = []
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

        # Setup logging (must happen before anything that logs)
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

        # Equity drawdown control state
        self._peak_equity = config.capital
        self._current_equity = config.capital
        self._load_equity_state()

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
        # Report requests (GetRealBalanceReport and friends) answer ASYNCHRONOUSLY
        # through this callback. Truncating to 100 chars and not keeping the text
        # meant the account equity never made it into any report.
        class SKReplyLibEvent:
            def OnReplyMessage(self, bstrUserID, bstrMessages):
                self_ref = self
                text = str(bstrMessages or "")
                self_ref._replies.append({
                    "ts": datetime.now().isoformat(), "user": str(bstrUserID or ""),
                    "text": text})
                self_ref.log.info(f"  [Reply] {bstrUserID}: {text[:2000]}")
                return -1

            def OnNewData(self, bstrUserID, bstrData):
                # Report requests answer HERE, not in OnReplyMessage: one comma
                # separated row per call, field 1 is the market/report type
                # (TS/TA/TL/R20...). Verified against the official sample
                # PythonExampleV2/Reply/Reply.py:68.
                self_ref = self
                row = str(bstrData or "")
                self_ref._data.append({
                    "ts": datetime.now().isoformat(), "user": str(bstrUserID or ""),
                    "row": row})
                return -1

            def OnData(self, bstrUserID, bstrData):
                # Some report types push here instead of OnNewData. Capture both so
                # the first real session settles which one the host actually uses.
                self_ref = self
                self_ref._data.append({
                    "ts": datetime.now().isoformat(), "user": str(bstrUserID or ""),
                    "row": str(bstrData or "")})
                return -1

            def OnComplete(self, bstrUserID):
                self_ref = self
                self_ref._data.append({"ts": datetime.now().isoformat(),
                                       "user": str(bstrUserID or ""), "row": "<COMPLETE>"})
                return -1

        reply_event = SKReplyLibEvent()
        reply_event.log = self.log
        # The callback object is not the trader, so hand it the same list object
        # (same trick as .log above). Appends then land in self._replies too.
        reply_event._replies = self._replies
        reply_event._data = self._report_rows
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

        # The reply host is a SEPARATE connection that must be opened explicitly
        # (official sample: PythonExampleV2/Reply/Reply.py:496). Without it every
        # report request returns SK_SUCCESS and then delivers nothing at all -
        # which is exactly what GetRealBalanceReport was doing.
        nCode = self.m_pSKReply.SKReplyLib_ConnectByID(self.user_id)
        self.log.info(f"  Reply host: "
                      f"{self.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)}")

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
                    trader_ref._note_ack(str(args))
                    return -1
                def OnFill(self_inner, *args):
                    trader_ref.log.info(f"  [FILL] {args}")
                    trader_ref._note_fill(str(args))
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
        """Current price. Same batched path the monitor uses."""
        return self._fetch_prices([stock_no]).get(stock_no, 0.0)

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
        self.borrowable_stocks, self._borrow_asof = get_borrowable_stocks()
        if self.borrowable_stocks is not None:
            self.log.info(f"  Borrowable (T-1 lending quota, as-of {self._borrow_asof}): "
                          f"{len(self.borrowable_stocks)} codes")
        else:
            self.log.warning(f"  LENDING QUOTA UNAVAILABLE ({self._borrow_asof}) "
                             f"- SHORT leg unverified, no filter applied")
        if self.restricted_stocks:
            self.log.info(f"  Loaded {len(self.restricted_stocks)} restricted stocks")

        # Load stock list
        stock_list = self._load_stock_list()
        self.log.info(f"  Stock universe: {len(stock_list)} codes")

        # The turnover floor needs the T-1 panel. It used to be loaded only
        # inside _score_signals, i.e. after the scan - so in live the floor at
        # line ~768 always fell back to the volume x open proxy and never saw
        # the real T-1 turnover the backtest used. Load it here instead.
        self._load_reference_panels()

        # Pre-open trim. Every filter below is decided by T-1 data, so a code
        # that fails one here can never become a signal - fetching its opening
        # price at 09:00 is pure waste. Measured 2026-10-26 against 124,596
        # historical trades: 98.6 pct of them already pass these filters, and
        # the 1.4 pct that do not are all prev_close < 30, which the live
        # config excludes anyway. Cutting first is behaviour-preserving.
        # (Tried and rejected: restricting to names that signalled in the last
        # 30 days - 737 codes, but that only covers 54.9 pct of trades.)
        stock_list = self._preopen_trim(stock_list)
        self.log.info(f"  Query list after pre-open filters: {len(stock_list)} codes")

        # TWSE API batch scan
        t0 = time.time()
        self.exec_stats["t_scan"] = t0
        self.exec_stats.setdefault("t_open", t0)
        raw_data, scan_source = self._batch_scan(stock_list)
        scan_time = time.time() - t0
        self.log.info(f"  Scan via {scan_source}: {len(raw_data)} quotes in {scan_time:.1f}s")

        # Coverage check. The model was trained on both markets, so a feed that
        # silently drops 上櫃 would be a train/serve mismatch worth ~2.6x CAGR
        # (measured: 44.6 pct of signals are 上櫃). Fail loudly instead.
        seen = {str(it.get("c")) for it in raw_data if it.get("n")}
        missing = [c for c in stock_list if c not in seen]
        tpex_seen = sum(1 for it in raw_data if it.get("x") == "TPEx")
        self.exec_stats["universe"] = len(stock_list)
        self.exec_stats["quoted"] = len(seen)
        self.exec_stats["unquoted"] = len(missing)
        self.exec_stats["tpex_quoted"] = tpex_seen
        if missing:
            self.log.warning(
                f"  COVERAGE: {len(missing)}/{len(stock_list)} codes returned no quote "
                f"({len(missing)/len(stock_list)*100:.0f}%). "
                f"Sample: {','.join(missing[:8])}")
        else:
            self.log.info(f"  COVERAGE: full universe answered "
                          f"(TPEx rows in feed: {tpex_seen})")
        self.exec_stats["scan_seconds"] = scan_time

        # Process: filter + gap detection
        total_valid = 0
        candidates = []
        self._nb_reject = 0
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

                # Price filter (v13: prev_close >= 30, no upper cap)
                if prev_close < self.config.min_price:
                    continue

                # T-1 daily turnover filter (v13: prev_turnover >= 10M TWD)
                t1tv = self._t1_turnover.get(stock_no)
                if t1tv is None:
                    t1tv = volume * open_price  # proxy when panel unavailable
                if t1tv < self._min_turnover_floor():
                    continue

                # Skip restricted (處置股)
                if stock_no in self.restricted_stocks:
                    continue

                # Calculate gap
                raw_gap = (open_price - prev_close) / prev_close

                # v13 benchmark: 0050 opening gap (observable at 09:00)
                if stock_no == self.config.benchmark_no:
                    self.benchmark_gap = raw_gap
                # legacy fallback (7 large caps) - NOT the v13 definition
                if stock_no in ("2330", "2317", "2454", "2303", "6505", "3711", "2412"):
                    gaps_for_market.append(raw_gap)

                candidates.append({
                    "symbol": stock_no,
                    "name": stock_name,
                    "openPrice": open_price,
                    "previousClose": prev_close,
                    "raw_gap": raw_gap,
                    "prev_turnover": float(t1tv),
                })
            except (ValueError, TypeError):
                continue

        # Market gap = 0050 opening gap (v13). Fallback only when 0050 unavailable.
        if getattr(self, "benchmark_gap", None) is not None:
            self.market_gap = self.benchmark_gap
            self.log.info(f"  Market gap (0050 open, v13 def): {self.market_gap*100:+.2f}%")
        elif gaps_for_market:
            self.market_gap = sum(gaps_for_market) / len(gaps_for_market)
            self.log.warning(f"  Market gap FALLBACK (7 large caps, NOT v13 def): {self.market_gap*100:+.2f}%")
        else:
            self.market_gap = 0.0
            self.log.warning("  Market gap unavailable -> using 0")

        # Filter by adjusted gap
        signals = []
        for c in candidates:
            adj_gap = c["raw_gap"] - self.market_gap

            direction = None
            if adj_gap >= self.config.gap_short_min:
                direction = Direction.SHORT
            elif adj_gap <= -self.config.gap_long_min:
                direction = Direction.LONG

            if direction is None:
                continue

            # Only SHORT needs a stock borrow. LONG is 現股買 and must not be
            # filtered here - that was a bug: it dropped valid LONG signals.
            if direction == Direction.SHORT and self.borrowable_stocks is not None \
                    and c["symbol"] not in self.borrowable_stocks:
                self._nb_reject += 1
                continue

            signals.append(Signal(
                symbol=c["symbol"], name=c["name"],
                direction=direction, open_price=c["openPrice"],
                prev_close=c["previousClose"], raw_gap=c["raw_gap"],
                adj_gap=adj_gap, prev_turnover=c.get("prev_turnover", 0.0),
            ))

        # Price limits + zt_dist + opening-lock flag (v13 excludes opening-locked)
        for sig in signals:
            lu, ld = calc_price_limits(sig.prev_close)
            sig.zhangting = lu
            sig.dieding = ld
            if sig.direction == Direction.SHORT:
                sig.zt_dist = (lu - sig.open_price) / sig.open_price
                sig.is_at_limit = sig.open_price >= lu - 1e-9
            else:
                sig.zt_dist = (sig.open_price - ld) / sig.open_price
                sig.is_at_limit = sig.open_price <= ld + 1e-9
        n_locked = sum(1 for s in signals if s.is_at_limit)
        self.log.info(f"  Opening-locked (excluded by v13): {n_locked}")
        if self.borrowable_stocks is None:
            self.log.warning("  SHORT leg NOT filtered for lending quota (see above)")
        else:
            self.log.info(f"  Rejected SHORT for no lending quota (T-1): {self._nb_reject}")


        # v13: model scoring + pred_q filter. NO top-N cap, NO gap-size ranking.
        self.signals = self._score_signals(signals)
        self.signals.sort(key=lambda x: -x.pred_q)

        self.log.info(f"  Scan done in {time.time()-t0:.1f}s ({total_valid} valid quotes)")
        self.log.info(f"  Raw gap signals {len(signals)} -> model-selected {len(self.signals)} "
                      f"(pred_q >= {self.config.pred_q_min}):")
        for sg in self.signals:
            self.log.info(
                f"    {sg.symbol} {sg.name:<8} {sg.direction.value:<5} "
                f"gap={sg.adj_gap*100:+.1f}% zt_dist={sg.zt_dist*100:4.1f}% "
                f"pred={sg.pred*100:+.2f}% q={sg.pred_q:.3f} q1={sg.q1:.3f} base={sg.base_pos*100:.0f}%")

        return self.signals

    # ----------------------------------------------------------
    # v13 MODEL SCORING (replaces Model B/C hand-scored regime)
    # ----------------------------------------------------------
    _v13_model = None
    _factor_row = None
    _t1_turnover: dict = {}

    def _load_v13_model(self):
        if self._v13_model is not None:
            return self._v13_model
        p = Path(self.config.model_path)
        if not p.exists():
            self.log.error(f"  v13 model missing: {p} -> no signals today")
            return None
        import pickle as _pk
        self._v13_model = _pk.load(open(p, "rb"))
        self.log.info(f"  v13 model loaded: trained through {self._v13_model['train_end']}, "
                      f"pool={len(self._v13_model['pool2'])}")
        return self._v13_model

    def _load_reference_panels(self):
        """Factor panel (already shifted to T-1) + T-1 turnover from the local store.

        Idempotent: scan_signals needs it before the pre-open trim, and
        _score_signals calls it again on the same run.
        """
        if getattr(self, "_panels_loaded", False):
            return
        self._panels_loaded = True
        self._factor_row = None
        self._factor_lag = None
        self._t1_turnover = {}
        try:
            import v13_factors as VF
            # tiny latest-row cache (~200KB) instead of the 1.7GB panel -> 9:00 safe
            row, tvrow, d = VF.latest()
            self._factor_row = row
            if tvrow is not None:
                self._t1_turnover = {str(k): float(v) for k, v in tvrow.dropna().items()}
            lag = (pd.Timestamp(datetime.now().date()) - pd.Timestamp(d)).days
            self._factor_lag = lag
            self.log.info(f"  Factor panel as-of {d} (lag {lag}d), turnover keys {len(self._t1_turnover)}")
            if lag > self.config.max_factor_lag_days:
                # The backtest never saw a value for these dates - the panel did
                # not cover them, so those rows were scored with NaN and
                # HistGradientBoosting routed them to its missing-value branch.
                # Substituting a frozen snapshot would make live diverge from the
                # backtest, and the measured sensitivity is asymmetric: dropping
                # all panel factors costs SHORT +2.4 pct RMSE but LONG +26.5 pct.
                # Match the backtest, and say so out loud.
                self.log.warning(
                    f"  FACTOR PANEL STALE by {lag}d (> {self.config.max_factor_lag_days}d). "
                    f"Feeding NaN factors, which is how the backtest scored these dates. "
                    f"Measured cost (same engine, only panel cols removed): 2023-25 segment "
                    f"1692% -> 260%. Run `python v13_factors.py --refresh` - it does work "
                    f"(finlab VIP), and is_vip()=False is a red herring under legacy token "
                    f"login. See LIVE_READINESS.md sec.7.")
                self._factor_row = None

        except Exception as e:
            self.log.warning(f"  Factor panel unavailable ({e}) -> model uses NaN factors")

    def _signal_history(self) -> dict:
        """{symbol: [iso dates]} of raw gap signals, for stock_signals_30d / had_signal_yesterday."""
        p = Path(self.config.log_dir) / "signal_history.json"
        if p.exists():
            try:
                import json as _j
                return _j.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _record_signal_history(self, signals):
        p = Path(self.config.log_dir) / "signal_history.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        hist = self._signal_history()
        today = datetime.now().strftime("%Y-%m-%d")
        for sig in signals:
            hist.setdefault(sig.symbol, [])
            if today not in hist[sig.symbol]:
                hist[sig.symbol].append(today)
            hist[sig.symbol] = hist[sig.symbol][-120:]
        import json as _j
        p.write_text(_j.dumps(hist), encoding="utf-8")

    def _hist_counts(self) -> dict:
        hist = self._signal_history()
        today = pd.Timestamp(datetime.now().date())
        out = {}
        for sym, ds in hist.items():
            dd = pd.to_datetime(pd.Series(ds))
            gap_days = (today - dd).dt.days
            c30 = int((gap_days <= 30).sum())
            hy = int(gap_days.min() == 1) if len(gap_days) else 0
            out[sym] = (c30, hy)
        return out

    def _trail_state_path(self) -> Path:
        return Path(self.config.log_dir) / "trail30_state.json"

    def _trail30(self, direction: str) -> float:
        """Trailing-30-trade realised PnL by direction (k_trail input).
        Seeded from the model export, updated from live results each day."""
        import json as _j
        p = self._trail_state_path()
        if p.exists():
            try:
                st = _j.loads(p.read_text(encoding="utf-8"))
                vals = st.get(direction, [])
                if len(vals) >= 10:
                    return float(sum(vals[-30:]) / len(vals[-30:]))
            except Exception:
                pass
        m = self._v13_model
        if m:
            return float(m["trailing30"].get(direction, 0.0))
        return 0.0

    def _update_trail30(self, trades: list):
        """Append today's realised per-trade PnL to the rolling state."""
        import json as _j
        if not trades:
            return
        p = self._trail_state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        st = {}
        if p.exists():
            try:
                st = _j.loads(p.read_text(encoding="utf-8"))
            except Exception:
                st = {}
        for direction, pnl in trades:
            st.setdefault(direction, []).append(float(pnl))
            st[direction] = st[direction][-60:]
        p.write_text(_j.dumps(st), encoding="utf-8")
        self.log.info(f"  trail30 updated: " + " ".join(
            f"{k}={sum(v[-30:])/len(v[-30:])*100:+.2f}%(n={len(v[-30:])})" for k, v in st.items()))

    @staticmethod
    def _quantile(pool: np.ndarray, vals: np.ndarray) -> np.ndarray:
        p = np.sort(np.asarray(pool, dtype=float))
        return np.searchsorted(p, np.asarray(vals, dtype=float), side="left") / len(p)

    def _score_signals(self, signals: list) -> list:
        """Run the two-pass walk-forward model, attach pred/q1/base_pos, drop pred_q < min."""
        import numpy as _np
        m = self._load_v13_model()
        if m is None or not signals:
            return []
        self._load_reference_panels()
        fac = self._factor_row
        mf = getattr(self, "_market_features", {})
        hc = self._hist_counts()
        today = datetime.now()
        rows = []
        for sig in signals:
            c30, hy = hc.get(sig.symbol, (0, 0))
            r = {
                "adj_gap": sig.adj_gap, "abs_gap": abs(sig.adj_gap), "zt_dist": sig.zt_dist,
                "market_ret": self.market_gap,
                "mkt_vol_5d": mf.get("vol_5d", 0.0), "mkt_drawdown": mf.get("drawdown", 0.0),
                "prev3_market_ret": mf.get("ret_3d", 0.0), "consec_down_days": mf.get("consec_down", 0),
                "signals_today": len(signals), "stock_signals_30d": c30, "had_signal_yesterday": hy,
                "month": today.month, "weekday": today.weekday(), "price": sig.prev_close,
            }
            if fac is not None and sig.symbol in fac.index:
                for c in fac.columns:
                    if c == "price":
                        continue
                    v = fac.loc[sig.symbol, c]
                    r[c] = float(v) if pd.notna(v) else _np.nan
            rows.append(r)
        X = pd.DataFrame(rows)
        # A column can be absent when the panel has no row for a candidate. The
        # models take NaN natively, so materialise the column rather than letting
        # X.loc[..., e["cols"]] raise KeyError on the whole batch.
        need = sorted({c for e in list(m["prod_models"].values()) + list(m["prod_models2"].values())
                       for c in e["cols"]})
        X = X.reindex(columns=list(X.columns) + [c for c in need if c not in X.columns])
        pr1 = _np.full(len(X), _np.nan); pr2 = _np.full(len(X), _np.nan)
        dirs = _np.array([s.direction.value for s in signals])
        for direc in ("SHORT", "LONG"):
            mask = dirs == direc
            if not mask.any():
                continue
            for key, target in (("prod_models", 1), ("prod_models2", 2)):
                e = m[key][direc]
                XX = X.loc[mask, e["cols"]].apply(pd.to_numeric, errors="coerce").values
                pv = e["model"].predict(XX)
                if target == 1:
                    pr1[mask] = pv
                else:
                    pr2[mask] = pv
        q1 = self._quantile(m["pool1"], _np.nan_to_num(pr1, nan=0.0))
        q2 = self._quantile(m["pool2"], _np.nan_to_num(pr2, nan=0.0))
        lad = _np.asarray(m["ladder"], dtype=float); cuts = list(m["cuts"])
        keep = []
        for i, sig in enumerate(signals):
            sig.pred = float(pr2[i]) if _np.isfinite(pr2[i]) else 0.0
            sig.q1 = float(q1[i]); sig.pred_q = float(q2[i])
            b = int(_np.searchsorted(_np.asarray(cuts), sig.pred_q, side="right")) - 1
            sig.base_pos = float(lad[max(0, min(b, len(lad) - 1))])
            sig._tp_pct = m["tp_high"] if sig.q1 >= m["q1_tp_threshold"] else m["tp_low"]
            sig._trail30 = m["trailing30"].get(sig.direction.value, 0.0)
            if sig.pred_q < self.config.pred_q_min:
                continue
            keep.append(sig)
        self._record_signal_history(signals)
        self.log.info(f"  Model scored {len(signals)} candidates -> kept {len(keep)}; "
                      f"TP20 share {sum(1 for k in keep if k._tp_pct >= 0.2)/max(1,len(keep))*100:.0f}%")
        return keep

    def _load_stock_list(self) -> list[str]:
        """Load stock codes from valid_stocks.txt."""
        path = self.config.stock_list_path
        if not path.exists():
            self.log.warning(f"  Stock list not found: {path}")
            path = path.parent / "all_stocks.txt"
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def _preopen_trim(self, stock_list: list[str]) -> list[str]:
        """Drop codes that cannot pass the scan filters, before asking for prices.

        Uses only information available before 09:00: T-1 turnover (already in
        self._t1_turnover) and today's disposal list (already in
        self.restricted_stocks). The price filter stays in scan_signals because
        prev_close only arrives with the quote.
        """
        keep = []
        dropped = {"turnover": 0, "disposal": 0, "no_turnover_data": 0}
        for code in stock_list:
            if code in self.restricted_stocks:
                dropped["disposal"] += 1
                continue
            t1tv = self._t1_turnover.get(code)
            if t1tv is None:
                # No panel row: keep it, scan_signals falls back to a
                # volume x price proxy and decides there. Dropping it would be
                # a stricter rule than the backtest applies.
                dropped["no_turnover_data"] += 1
                keep.append(code)
                continue
            if t1tv < self._min_turnover_floor():
                dropped["turnover"] += 1
                continue
            keep.append(code)
        self.log.info(
            f"  Pre-open trim: dropped {dropped['turnover']} below turnover floor, "
            f"{dropped['disposal']} disposal, kept {len(keep)} "
            f"({dropped['no_turnover_data']} without panel data, decided at scan)")
        return keep

    def _fugle_session(self) -> requests.Session:
        """Cached session so repeated quote polls reuse one TLS connection."""
        sess = getattr(self, "_fugle_sess", None)
        if sess is None:
            sess = requests.Session()
            sess.headers.update({"X-API-KEY": self.config.fugle_api_key})
            self._fugle_sess = sess
        return sess

    def _fetch_prices(self, codes: list[str]) -> dict[str, float]:
        """Last price for many symbols in ONE request.

        Measured 2026-10-26: 22 symbols = 0.47s batched vs 11.23s one-by-one.
        The SL/TP monitor used to poll each position separately, so 22 open
        positions left an 11s blind spot between two checks - longer than it
        takes a gap stock to run through its stop.
        """
        out = {}
        uniq = [c for c in dict.fromkeys(codes) if c]
        if not uniq:
            return out
        session = self._fugle_session()
        size = max(1, self.config.fugle_batch_size)
        for i in range(0, len(uniq), size):
            batch = uniq[i:i + size]
            try:
                r = session.get(self.config.fugle_batch_url,
                                params={"symbol": ",".join(batch)}, timeout=10)
                if r.status_code != 200:
                    self.log.warning(f"  Fugle price batch {r.status_code}: "
                                     f"{r.text[:100]}")
                    continue
                rows = r.json()
            except Exception as exc:
                self.log.warning(f"  Fugle price batch error: {exc}")
                continue
            for q in rows:
                try:
                    price = float(q.get("lastPrice") or 0)
                except (TypeError, ValueError):
                    continue
                if price > 0:
                    out[str(q.get("symbol", ""))] = price
        return out

    def _fugle_batch_scan(self, stock_list: list[str]) -> list[dict]:
        """Batch-query Fugle `intraday/quotes?symbol=...` for the WHOLE market.

        Returns rows shaped like TWSE MIS `msgArray` entries (c/n/o/y/v) so the
        rest of scan_signals is source-agnostic. Unlike TWSE MIS this carries
        上櫃 (TPEx) as well as 上市, which is where ~43 pct of the model's
        signals come from.
        """
        session = requests.Session()
        session.headers.update({"X-API-KEY": self.config.fugle_api_key})

        def query_batch(codes):
            try:
                r = session.get(self.config.fugle_batch_url,
                                params={"symbol": ",".join(codes)}, timeout=20)
                if r.status_code != 200:
                    self.log.warning(f"  Fugle batch {r.status_code}: {r.text[:120]}")
                    return []
                return r.json()
            except Exception as exc:
                self.log.warning(f"  Fugle batch error: {exc}")
                return []

        size = self.config.fugle_batch_size
        batches = [stock_list[i:i+size] for i in range(0, len(stock_list), size)]
        rows = []
        for b in batches:                      # 4 requests for 3.3k codes; no
            for q in query_batch(b):          # parallelism -> no 429s
                vol = (q.get("total") or {}).get("tradeVolume") or 0
                rows.append({
                    "c": str(q.get("symbol", "")),
                    "n": q.get("name", "") or "",
                    "o": q.get("openPrice"),
                    "y": q.get("previousClose"),
                    "v": vol,
                    "x": q.get("exchange", ""),
                    # RISK1 needs both of these. `date` says which session the
                    # feed is on (it keeps answering with the last trading day
                    # when today is closed), and `openTime` is the exchange
                    # opening print in microseconds epoch - measured 2026-10-22
                    # 2330 openTime = 09:00:08.980736, i.e. the opening price
                    # of the most liquid stock in the market was not printable
                    # at 09:00:00.000. TWSE MIS has neither, so the fallback
                    # path reports 0 and says so.
                    "d": q.get("date", ""),
                    "ot": q.get("openTime") or 0,
                })
        return rows

    def _batch_scan(self, stock_list: list[str]) -> tuple[list[dict], str]:
        """Primary = Fugle (both markets). Fallback = TWSE MIS (上市 only)."""
        try:
            rows = self._fugle_batch_scan(stock_list)
            got = {r["c"] for r in rows if r.get("n")}
            if len(got) >= max(1, int(len(stock_list) * 0.6)):
                return rows, "Fugle (TWSE+TPEx)"
            self.log.warning(f"  Fugle answered only {len(got)}/{len(stock_list)} "
                             f"codes, falling back to TWSE MIS")
        except Exception as exc:
            self.log.warning(f"  Fugle scan failed ({exc}), falling back to TWSE MIS")
        return self._twse_batch_scan(stock_list), "TWSE MIS (上市 only)"

    def _twse_batch_scan(self, stock_list: list[str]) -> list[dict]:
        """Batch-query TWSE API. 100 codes/request, 15 parallel workers."""
        TWSE_API = "http://mis.twse.com.tw/stock/api/getStockInfo.jsp"
        BATCH_SIZE = 100
        MAX_WORKERS = 15

        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        adapter = requests.adapters.HTTPAdapter(pool_connections=25, pool_maxsize=25)
        session.mount("http://", adapter)

        def query_batch(codes, prefix="tse"):
            parts = [f"{prefix}_{c}.tw" for c in codes]
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

        # MIS answers 上櫃 only under the otc_ prefix (learned from
        # twjackysu/TWSEMCPServer). Without this the fallback silently returns
        # nothing for every TPEx code. Measured 2026-10-26: otc_ recovers
        # 1,403 of 1,775 TPEx codes; the other 372 are real tradeable stocks
        # MIS does not carry at all (1260 富味鄉, 1269 乾杯, 1293 利統, ...), which
        # is why Fugle stays the primary source.
        found = {str(it.get("c")) for it in all_raw if it.get("c")}
        missing = [c for c in stock_list if c not in found]
        if missing:
            otc_batches = [missing[i:i+BATCH_SIZE]
                           for i in range(0, len(missing), BATCH_SIZE)]
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = [executor.submit(query_batch, b, "otc") for b in otc_batches]
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
        orders_placed = 0

        skipped_at_limit = 0
        skipped_impact_capped = 0
        skipped_lot_coarse = 0
        skipped_order_cap = 0

        for sig in self.signals:
            # Operational cap: signals are sorted by pred_q desc, so everything after the
            # cap is lower-ranked anyway. Stop instead of continuing to save API calls.
            if orders_placed >= self.config.max_orders_per_day:
                skipped_order_cap = len(self.signals) - orders_placed
                break
            if sig.is_at_limit:
                skipped_at_limit += 1
                continue

            # Use open price as entry (immediate execution at market open)
            entry_price = sig.open_price

            # ===== v13 sizing: base_pos x zt_mult x dd_scale x k_model x k_trail =====
            if sig.zt_dist < self.config.zt_bp1:
                zt_mult = self.config.zt_m1
            elif sig.zt_dist < self.config.zt_bp2:
                zt_mult = self.config.zt_m2
            else:
                zt_mult = 1.0

            peak = max(self._peak_equity, self._current_equity)
            dd = (self._current_equity - peak) / peak if peak > 0 else 0.0
            if dd < -self.config.dd_th2:
                dd_scale = self.config.dd_scale2
            elif dd < -self.config.dd_th1:
                dd_scale = self.config.dd_scale1
            else:
                dd_scale = 1.0

            k_model = (min(2.0, max(0.0, 0.5 + sig.pred / self.config.k_model_scale))
                       if self.config.use_k_model else 1.0)
            t30 = self._trail30(sig.direction.value)
            k_trail = min(2.0, max(0.3, 0.5 + t30 / self.config.k_trail_scale))

            pos_pct = min(sig.base_pos * self.config.position_multiplier * zt_mult
                          * dd_scale * k_model * k_trail, self.config.pos_cap_pct)
            if pos_pct < self.config.min_pos_pct:
                self.log.info(f"  {sig.symbol}: pos {pos_pct*100:.2f}% < min "
                              f"{self.config.min_pos_pct*100:.1f}%, SKIP (cannot fill 1 zhang)")
                continue
            sig._pos_pct = pos_pct
            sig.tier = f"q{sig.pred_q:.2f}/zt{zt_mult:.1f}/dd{dd_scale:.2f}/km{k_model:.1f}/kt{k_trail:.1f}"

            budget = self._current_equity
            # R6 sizing (v13_sizing_lab.py, measured 2026-10-27): skip names whose
            # 1-lot value exceeds the cap, cap notional per trade, floor to lots.
            lot_value = entry_price * 1000
            dynamic_floor = self.config.max_lot_value_pct * budget
            if lot_value > dynamic_floor:
                self.log.info(f"  {sig.symbol}: 1 zhang = {lot_value:,.0f} > "
                              f"25% equity ({dynamic_floor:,.0f}), SKIP (lot too coarse)")
                skipped_lot_coarse += 1
                continue
            target_value = min(pos_pct * budget, self.config.max_per_trade_pct * budget)
            # Liquidity filter: dynamic 5% participation rate.
            # min_turnover = 5 x equity. Scales with capital automatically.
            t1tv = float(getattr(sig, "prev_turnover", 0.0) or 0.0)
            min_tv = self._min_turnover_floor()
            if t1tv > 0 and t1tv < min_tv:
                self.log.info(f"  {sig.symbol}: T-1 turnover {t1tv/1e6:.0f}M < "
                              f"min {min_tv/1e6:.0f}M (5% participation), SKIP")
                skipped_impact_capped += 1
                continue
            shares = int(target_value / lot_value) * 1000
            if shares < 1000:
                self.log.info(f"  {sig.symbol}: < 1 zhang after sizing, SKIP")
                continue

            # Zero-margin hard cap: total notional <= equity (sequential, shrink to fit)
            room = budget * self.config.max_total_exposure - total_exposure
            if room < shares * entry_price:
                shares = int(max(0.0, room) / (entry_price * 1000)) * 1000
                if shares < 1000:
                    self.log.info(f"  {sig.symbol}: exposure cap reached, SKIP")
                    continue
            actual_value = shares * entry_price
            total_exposure += actual_value

            # Set entry/SL/TP
            sig.entry_price = entry_price
            sig.shares = shares

            # Dynamic SL: min(4 pct, price_limit - 1 tick). Always reachable, never locked.
            sl_price, sl_pct = calc_effective_sl(
                entry_price, sig.prev_close, sig.direction,
                self.config.stop_loss_pct)
            sig.sl_price = sl_price
            sig._sl_pct = sl_pct  # store for Smart Trade

            tp_pct = self._get_tp_pct(sig)
            if sig.direction == Direction.SHORT:
                sig.tp_price = snap_to_valid_price(entry_price * (1 - tp_pct))
            else:
                sig.tp_price = snap_to_valid_price(entry_price * (1 + tp_pct))
            sig._tp_pct = tp_pct

            limit_up, limit_down = calc_price_limits(sig.prev_close)
            self.log.info(
                f"  ENTER {sig.symbol} {sig.direction.value} "
                f"price={entry_price} shares={shares} tier={sig.tier} "
                f"SL={sig.sl_price}({getattr(sig, '_sl_pct', 0)*100:.1f}%) "
                f"TP={sig.tp_price}({getattr(sig, '_tp_pct', 0)*100:.0f}%) | limit={limit_up}/{limit_down}")

            # Place order
            self._place_entry_order(sig)
            orders_placed += 1

        self.exec_stats["t_submit_last"] = time.time()
        if skipped_at_limit:
            self.log.info(f"  Skipped (at price limit): {skipped_at_limit}")
        if skipped_impact_capped:
            self.log.info(f"  Skipped (T-1 turnover < {self.config.min_turnover_factor}x equity, "
                          f"5 pct participation cap): {skipped_impact_capped}")
        if skipped_lot_coarse:
            self.log.info(f"  Skipped (1 zhang > {self.config.max_lot_value_pct*100:.0f}% of equity, "
                          f"lot too coarse): {skipped_lot_coarse}")
        if skipped_order_cap:
            self.log.warning(f"  ORDER CAP HIT: {skipped_order_cap} lower-ranked signals not sent "
                             f"(cap {self.config.max_orders_per_day}). Check candidate count.")
        self.log.info(f"  Orders placed: {orders_placed}")
        self.log.info(
            f"  Total exposure: {total_exposure:,.0f} "
            f"({total_exposure/self.config.capital*100:.0f}%)")

    def _fetch_market_history(self):
        """Fetch TSEC weighted index history via Yahoo Finance. Call before scan."""
        import requests
        try:
            # Yahoo Finance: ^TWII = TWSE Capitalization Weighted Index
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII"
            params = {"range": "2y", "interval": "1d"}
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()
            result = data["chart"]["result"][0]
            raw_closes = result["indicators"]["quote"][0]["close"]
            stamps = result.get("timestamp", [])
            # v13 market features are strictly T-1: drop any bar stamped today
            today = pd.Timestamp(datetime.now().date())
            hist = []
            for i, c in enumerate(raw_closes):
                if c is None:
                    continue
                if i < len(stamps) and pd.Timestamp(pd.to_datetime(stamps[i], unit="s")).normalize() >= today:
                    continue
                hist.append(c)
            self._market_history = hist
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

        # Drawdown from cumulative high (v13 def: close/cummax - 1, as of T-1)
        high_all = max(hist)
        current = hist[-1]
        drawdown = (current - high_all) / high_all

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

    def _get_tp_pct(self, sig) -> float:
        """v13 TP: 20 pct when q1 >= 0.85 (top decile of pass-1 prediction), else 12 pct."""
        return float(getattr(sig, "_tp_pct", self.config.take_profit_pct))

    # ----------------------------------------------------------
    # EXECUTION TELEMETRY (pre-live risk measurement)
    # ----------------------------------------------------------
    fill_events: dict = {}
    fill_prices: dict = {}
    fill_raw: dict = {}
    exec_stats: dict = {}

    def _note_fill(self, raw: str):
        """Record fill time, and try to recover the fill price.

        Time alone is not enough to review a live session: the number that
        decides whether the backtest is real is the fill PRICE versus the price
        we intended to trade at. The SKCOM OnFill argument layout is not
        documented in the wrapper and I have not seen a live fill, so instead of
        hard-coding a positional index I identify the price by plausibility -
        the intended entry is known and a same-day fill cannot be outside the
        price limits. The field index is logged so the first live session
        reveals the real layout and this guess-work can be replaced by a direct
        index. Ambiguous cases are logged, never guessed.
        """
        import re as _re
        code = _re.search(r"\b(\d{4,5})\b", raw)
        if not code:
            return
        sym = code.group(1)
        self.fill_events.setdefault(sym, []).append(time.time())
        self.fill_raw.setdefault(sym, []).append(raw)

        sig = self.active_positions.get(sym)
        intended = float(getattr(sig, "entry_price", 0) or 0) if sig else 0.0
        if intended <= 0:
            return
        # calc_price_limits returns (limit_up, limit_down) - naming them lo/hi
        # in the wrong order silently inverts the window and nothing ever
        # matches, so sort explicitly.
        lim_a, lim_b = calc_price_limits(intended)
        lo, hi = min(lim_a, lim_b), max(lim_a, lim_b)
        # Drop quoted fields first. The stock code is itself a number and for
        # many names it lands inside the price band (2330 at 2435 has a
        # 2195-2675 window), so parsing the raw tuple would call the code a
        # price. Prices and quantities are bare numbers; symbols and broker ids
        # are quoted. Indices below therefore count NUMERIC fields, not tuple
        # positions - enough to identify the layout on the first live run.
        body = _re.sub(r"'[^']*'", " ", raw)
        cand = []
        for i, tok in enumerate(_re.findall(r"-?\d+\.?\d*", body)):
            try:
                v = float(tok)
            except ValueError:
                continue
            if v >= 1 and lo <= v <= hi:
                cand.append((i, v))
        uniq = sorted({v for _, v in cand})
        if len(uniq) == 1:
            self.fill_prices.setdefault(sym, []).append(uniq[0])
            if sig is not None:
                sig.fill_price = uniq[0]
            if not self.exec_stats.get("fill_field_index_logged"):
                self.exec_stats["fill_field_index_logged"] = True
                self.log.info(
                    f"  [FILL] price recovered at numeric field "
                    f"#{cand[0][0]} ({sym} -> {uniq[0]}) - if that is right, "
                    f"hard-code the index in _note_fill")
        else:
            self.log.warning(
                f"  [FILL] {sym}: cannot isolate the fill price "
                f"(intended={intended}, price window {lo}-{hi}, "
                f"candidates={cand[:8]}) - raw args are in the log above")

    def _note_ack(self, raw: str):
        self.exec_stats.setdefault("acks", []).append((time.time(), raw[:200]))

    def _exec_report(self):
        """Summarise submit->ack latency, fill latency and reject counts."""
        st = self.exec_stats
        lat = [r["ack_latency"] for r in st.get("orders", []) if r.get("ack_latency") is not None]
        rej = [r for r in st.get("orders", []) if r.get("ack_code") not in (0, None)]
        retr = [r for r in st.get("orders", []) if r.get("retries", 0) > 0]
        t_open = st.get("t_open")
        fills = []
        for sym, ts in self.fill_events.items():
            if t_open:
                fills.append(min(ts) - t_open)
        self.log.info("=" * 60)
        self.log.info("EXECUTION RISK REPORT")
        if st.get("quote_latency_s") is not None:
            self.log.info(f"  RISK1 opening price visible: {st['quote_latency_s']:.2f}s after 09:00:00")
        if st.get("t_scan_done") and t_open:
            self.log.info(f"  RISK1 scan finished: {st['t_scan_done']-t_open:.2f}s after 09:00:00 "
                          f"(scan itself took {st.get('scan_seconds', 0):.1f}s)")
        if st.get("universe"):
            miss = st.get("unquoted", 0)
            self.log.info(f"  MARKET COVERAGE: {st['quoted']}/{st['universe']} codes answered, "
                          f"{miss} silent (上櫃/ETF, not on the TWSE feed) = "
                          f"{miss/st['universe']*100:.0f}% of the universe not traded")
        if lat:
            lat_s = sorted(lat)
            self.log.info(f"  submit->ack  n={len(lat)} median={lat_s[len(lat_s)//2]*1000:.0f}ms "
                          f"p95={lat_s[int(len(lat_s)*0.95)]*1000:.0f}ms max={max(lat)*1000:.0f}ms")
        if st.get("t_submit_first") and st.get("t_submit_last"):
            n = len(st.get("orders", []))
            span = st["t_submit_last"] - st["t_submit_first"]
            self.log.info(f"  order submission: {n} orders in {span:.1f}s "
                          f"({n/span if span>0 else 0:.2f} orders/s) -> scan-to-all-submitted "
                          f"{(st['t_submit_last']-st.get('t_scan',st['t_submit_first'])):.1f}s")
        if fills:
            fs = sorted(fills)
            for w in (5, 10, 30, 60):
                self.log.info(f"  filled within {w:>2}s of 09:00: {sum(1 for x in fs if x<=w)}/{len(fs)}")
            self.log.info(f"  first-fill latency median={fs[len(fs)//2]:.1f}s")
        self.log.info(f"  rejected orders: {len(rej)}  retried: {len(retr)}")
        for r in rej[:10]:
            self.log.info(f"    {r['symbol']} code={r['ack_code']} {r.get('msg','')}")

        # Entry slippage. The backtest fills at the 09:00:00 opening price;
        # reality fills seconds later at a different price. This is the one
        # number that says how much of the modelled edge survives contact with
        # the market, and it is direction-dependent: filling higher than
        # intended helps a SHORT entry (we sell dearer) and hurts a LONG one.
        # edge > 0 always means favourable.
        slips = {"SHORT": [], "LONG": []}
        for sym, prices in self.fill_prices.items():
            sig = self.active_positions.get(sym)
            intended = float(getattr(sig, "entry_price", 0) or 0) if sig else 0.0
            if intended <= 0:
                continue
            d = getattr(sig, "direction", None)
            dname = d.value if d in (Direction.SHORT, Direction.LONG) else None
            if dname not in slips:
                continue
            fill = prices[0]
            slip = (fill - intended) / intended
            slips[dname].append((sym, intended, fill, slip,
                                 slip if dname == "SHORT" else -slip))
        got = [x for v in slips.values() for x in v]
        if got:
            self.log.info(f"  ENTRY SLIPPAGE vs the price the backtest assumed "
                          f"(n={len(got)}, edge>0 = favourable):")
            for dname in ("SHORT", "LONG"):
                rows = slips[dname]
                if not rows:
                    continue
                edges = sorted(r[4] for r in rows)
                med = edges[len(edges) // 2]
                p90 = edges[min(len(edges) - 1, int(0.9 * len(edges)))]
                self.log.info(f"    {dname} n={len(rows)} median_edge={med*100:+.3f}% "
                              f"p90_edge={p90*100:+.3f}% "
                              f"mean={sum(edges)/len(edges)*100:+.3f}%")
                for sym, intended, fill, slip, edge in rows[:10]:
                    self.log.info(f"      {sym} intended={intended} filled={fill} "
                                  f"slip={slip*100:+.3f}% edge={edge*100:+.3f}%")
        else:
            accepted = [o for o in self.exec_stats.get("orders", [])
                        if o.get("ack_code") == 0]
            if not accepted:
                # Nothing was accepted, so there is no fill to compare against.
                # In paper mode that is the designed outcome (probe orders are
                # priced so they cannot fill) - telling the reader to go fix a
                # field index would chase a bug that does not exist.
                self.log.info("  ENTRY SLIPPAGE: not measurable - no order was "
                              "accepted, so there is no fill to compare. In paper "
                              "mode this is expected; the slippage figure comes "
                              "from the paper report's own section instead.")
            else:
                self.log.warning("  ENTRY SLIPPAGE: not measurable - no fill price "
                                 "could be recovered from the OnFill args. The raw "
                                 "args are in this log; use them to fix the field "
                                 "index in _note_fill.")
        try:
            import json as _j
            p = Path(self.config.log_dir) / f"exec_report_{datetime.now().strftime('%Y%m%d')}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_j.dumps({"stats": {k: v for k, v in st.items() if k != "acks"},
                                   "fills": {k: [x - (t_open or x) for x in v] for k, v in self.fill_events.items()},
                                   "fill_prices": self.fill_prices,
                                   "fill_raw": {k: v[:3] for k, v in self.fill_raw.items()}},
                                  default=str, indent=1), encoding="utf-8")
            self.log.info(f"  saved {p}")
        except Exception as e:
            self.log.warning(f"  exec report save failed: {e}")

    def _place_entry_order(self, sig: Signal):
        """Place one Smart Trade day-trade order: entry + SL + TP + time clear.

        Field semantics come from the Capital manual
        (6.下單-證券智慧單.docx, struct STOCKSTRATEGYORDER / 證券當沖):
          nQty                = 委託張數, NOT share count (1 張 = 1000 股)
          nBuySell            = 0:現股買 / 1:無券賣出
          nRDOSLPercent = 0   -> stop loss fires on an absolute price (bstrSLTrigger)
          nRDOTPPercent = 0   -> take profit fires on an absolute price (bstrTPTrigger)
          bstrClearCancelTime = hhmm, the host accepts at most 13:20
        The absolute-price stop is what makes the live order match the backtest:
        calc_effective_sl() already caps the stop at 漲停 - 1 tick, and a
        percentage stop could never fire once the stock is pinned at 漲停.
        """
        oOrder = sk.STOCKSTRATEGYORDER()
        oOrder.bstrFullAccount = self.account
        oOrder.bstrStockNo = sig.symbol
        oOrder.nQty = max(1, int(sig.shares) // 1000)   # 張數
        oOrder.bstrOrderPrice = str(sig.entry_price)
        oOrder.nOrderPriceType = 2                      # LIMIT
        oOrder.nOrderPriceCond = 0                      # ROD

        # Buy/Sell: 0=現股買, 1=無券賣出 (no lending fee on this account)
        oOrder.nBuySell = 1 if sig.direction == Direction.SHORT else 0

        # Entry is a plain limit, not an MIT trigger
        oOrder.nInnerOrderIsMIT = 0
        oOrder.nMITDir = 0
        oOrder.bstrMITTriggerPrice = "0"
        oOrder.bstrMITDealPrice = "0"

        # Stop loss on an absolute price (already capped by the price limit)
        oOrder.nStopLossFlag = 1
        oOrder.nRDOSLPercent = 0
        oOrder.bstrSLTrigger = str(sig.sl_price)
        oOrder.bstrSLPercent = "0"
        oOrder.bstrSLOrderPrice = "0"
        oOrder.nRDSLMarketPriceType = 1                 # market order once triggered
        oOrder.nStopLossOrderCond = 0

        # Take profit on an absolute price
        oOrder.nTakeProfitFlag = 1
        oOrder.nRDOTPPercent = 0
        oOrder.bstrTPTrigger = str(sig.tp_price)
        oOrder.bstrTPPercent = "0"
        oOrder.bstrTPOrderPrice = "0"
        oOrder.nRDTPMarketPriceType = 1                 # market order once triggered
        oOrder.nTakeProfitOrderCond = 0

        # Time clear. The host rejects anything later than 13:20, and only a
        # market order guarantees the position is flat before the close.
        oOrder.nClearAllFlag = 1
        oOrder.bstrClearCancelTime = "1320"
        oOrder.nClearAllPriceType = 1                   # market
        oOrder.bstrClearAllOrderPrice = "0"
        oOrder.nClearOrderCond = 0
        oOrder.nFinalClearFlag = 0

        zhang = oOrder.nQty
        rec = {"symbol": sig.symbol, "direction": sig.direction.value,
               "shares": sig.shares, "zhang": zhang,
               "price": sig.entry_price, "sl": sig.sl_price, "tp": sig.tp_price,
               "pos_pct": round(getattr(sig, "_pos_pct", 0.0), 4),
               "retries": 0, "ack_latency": None, "ack_code": None, "msg": ""}
        self.exec_stats.setdefault("orders", []).append(rec)
        self.exec_stats["t_submit_first"] = min(self.exec_stats.get("t_submit_first", time.time()), time.time())
        try:
            t_sent = time.time()
            sig.submit_ts = t_sent
            bstrMessage, nCode = self.m_pSKOrder.SendStockStrategyDayTrade(
                self.user_id, False, oOrder)
            sig.ack_ts = time.time(); rec["ack_latency"] = sig.ack_ts - t_sent
        except Exception as e:
            err_str = str(e)
            if '924' in err_str or '不支持' in err_str or 'not support' in err_str.lower():
                self.log.warning(f"  {sig.symbol}: Does not support day trade, SKIP")
            else:
                self.log.error(f"  {sig.symbol}: Smart Trade exception - {e}")
            sig.state = PositionState.CANCELLED
            rec["msg"] = str(e)[:200]
            return

        rec["ack_code"] = nCode
        sig.ack_code = nCode
        sig.ack_msg = str(bstrMessage)
        if nCode == 0:
            sig.order_seq = bstrMessage
            sig.smart_key = _parse_smart_key(str(bstrMessage))
            sig.state = PositionState.FILLED
            self.active_positions[sig.symbol] = sig
            self.log.info(
                f"  SMART ORDER: {sig.symbol} {sig.direction.value} {zhang} 張 "
                f"@ {sig.entry_price} [{sig.tier}] "
                f"SL={sig.sl_price} TP={sig.tp_price} clear=13:20 "
                f"key={sig.smart_key}")
        else:
            msg = self.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
            rec["msg"] = str(msg)
            # The SDK's own text for a code is just the code ("924"). The
            # broker's actual reason - "投資人未具有上市股票當沖資格(無券當沖)" -
            # only ever arrived in bstrMessage and was logged then dropped, so
            # the report could not say what to go fix. Keep it on the record.
            rec["broker_msg"] = str(bstrMessage)
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

            # Update prices for reporting (every 60s, one batched call)
            if int(now.timestamp()) % 60 < 5:
                symbols = [s for s, sig in self.active_positions.items()
                           if sig.state in (PositionState.FILLED, PositionState.MONITORING)]
                if symbols:
                    for sym, price in self._fetch_prices(symbols).items():
                        sig = self.active_positions.get(sym)
                        if sig is None:
                            continue
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
        self._cancel_open_smart_orders()

    def _cancel_open_smart_orders(self):
        """Drop any smart order still armed at the end of the session.

        The host keeps a day-trade smart order until its 13:20 clear, so anything
        still armed here is either already filled-and-exited or never filled.
        Leaving it armed is how orphan orders show up in the App the next day.
        """
        if not getattr(self, "m_pSKOrder", None):
            return
        n = 0
        for sig in self.active_positions.values():
            if not getattr(sig, "smart_key", ""):
                continue
            if sig.exit_reason in ("MANUAL", "CANCELLED"):
                continue
            try:
                code, msg = cancel_smart_order(self.m_pSKOrder, self.user_id,
                                               self.account, sig.smart_key)
                self.log.info(f"  cancel smart {sig.symbol} key={sig.smart_key} -> {code} {msg}")
                n += 1 if code == 0 else 0
            except Exception as e:
                self.log.warning(f"  cancel smart {sig.symbol} failed: {str(e)[:150]}")
        if n:
            self.log.info(f"  Cancelled {n} smart order(s)")

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
        symbols = [s for s, sig in self.active_positions.items()
                   if sig.state in (PositionState.FILLED, PositionState.MONITORING)]
        if not symbols:
            return
        prices = self._fetch_prices(symbols)
        for symbol, sig in list(self.active_positions.items()):
            if sig.state not in (PositionState.FILLED, PositionState.MONITORING):
                continue
            price = prices.get(symbol, 0)
            if price <= 0:
                price = sig.entry_price
            self._mark_exit(sig, price, "FORCE_CLOSE")

    # ----------------------------------------------------------
    # STEP 4: REPORT
    # ----------------------------------------------------------

    def daily_report(self):
        try:
            done = []
            for t in self.closed_trades:
                e, x = float(t["entry"]), float(t["exit"])
                if e <= 0 or x <= 0:
                    continue
                r = (e - x) / e if t["direction"] == "SHORT" else (x - e) / e
                done.append((t["direction"], r))
            self._update_trail30(done)
        except Exception as e:
            self.log.warning(f"  trail30 update failed: {e}")
        try:
            self._exec_report()
        except Exception as e:
            self.log.warning(f"  exec report failed: {e}")
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

        # Update equity state
        self._current_equity += total_pnl
        if self._current_equity > self._peak_equity:
            self._peak_equity = self._current_equity
        self._save_equity_state()
        self.log.info(f"  Equity: {self._current_equity:,.0f} (peak: {self._peak_equity:,.0f})")

    def _load_equity_state(self):
        """Load peak/current equity from persistent state file."""
        try:
            path = self.config.equity_state_path
            if path.exists():
                import json
                state = json.loads(path.read_text(encoding='utf-8'))
                self._peak_equity = state.get('peak_equity', self.config.capital)
                self._current_equity = state.get('current_equity', self.config.capital)
                self.log.info(f"  Loaded equity state: peak={self._peak_equity:,.0f} current={self._current_equity:,.0f}")
        except Exception as e:
            self.log.warning(f"  Failed to load equity state: {e}")

    def _save_equity_state(self):
        """Persist peak/current equity for drawdown control across sessions."""
        try:
            import json
            path = self.config.equity_state_path
            path.parent.mkdir(parents=True, exist_ok=True)
            state = {
                'peak_equity': self._peak_equity,
                'current_equity': self._current_equity,
                'updated': datetime.now().isoformat()
            }
            path.write_text(json.dumps(state, indent=2), encoding='utf-8')
        except Exception as e:
            self.log.warning(f"  Failed to save equity state: {e}")

    def _min_turnover_floor(self) -> float:
        """Dynamic T-1 turnover floor = min_turnover_factor x current equity.

        One-way participation stays 5 pct: max position is 25 pct of equity,
        so 25 / 5 = 5 pct of the stock T-1 turnover. Scales with capital
        (4.5M -> 2250wan, 10M -> 5000wan, 20M -> 1yi). No absolute floor.
        """
        return self.config.min_turnover_factor * self._current_equity

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
            # Anchor every latency measurement to the real 09:00:00, not to the
            # moment the scan happens to start.
            self.exec_stats["t_open"] = self._parse_time("09:00").timestamp()
            self._wait_for_quotes(min_stocks=200, timeout_sec=10)
            self.scan_signals()
            self.exec_stats["t_scan_done"] = time.time()

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
        """Block until the scanner's own feed exposes opening prices.

        This used to poll SKQuoteLib, which fills in at a different speed than
        the TWSE API the scanner actually reads, so it gave a misleading answer.
        Probing the same source is also the only way to measure the one thing the
        backtest cannot know: how many seconds after 09:00:00 the first usable
        opening price is visible (RISK 1).
        """
        probe = self._load_stock_list()[:100]
        t_open = self.exec_stats.get("t_open") or time.time()
        deadline = time.time() + timeout_sec
        need = max(1, int(len(probe) * 0.9))
        got = 0
        while time.time() < deadline:
            rows, _ = self._batch_scan(probe)
            got = sum(1 for r in rows
                      if _to_float(r.get("o")) > 0 and _to_float(r.get("y")) > 0)
            if got >= need:
                lat = time.time() - t_open
                self.exec_stats["t_quotes_ready"] = time.time()
                self.exec_stats["quote_latency_s"] = lat
                self.log.info(f"  Quotes ready: {got}/{len(probe)} opening prices, "
                              f"{lat:.2f}s after market open")
                return
            self.log.info(f"  Waiting for quotes... ({got}/{need})")
            time.sleep(0.5)
        lat = time.time() - t_open
        self.exec_stats["t_quotes_ready"] = time.time()
        self.exec_stats["quote_latency_s"] = lat
        self.log.warning(f"  Timeout: only {got}/{need} opening prices visible "
                         f"{lat:.2f}s after market open")

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
        symbols = [s for s, sig in self.active_positions.items()
                   if sig.state in (PositionState.FILLED, PositionState.MONITORING)]
        prices = self._fetch_prices(symbols)
        for symbol, sig in list(self.active_positions.items()):
            if sig.state not in (PositionState.FILLED, PositionState.MONITORING):
                continue
            price = prices.get(symbol, 0)
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
        """Monitor for max 30 minutes, one batched price call per loop"""
        end_time = datetime.now().timestamp() + 1800  # 30 min

        while self.running and datetime.now().timestamp() < end_time:
            symbols = [s for s, sig in self.active_positions.items()
                       if sig.state in (PositionState.FILLED, PositionState.MONITORING)]
            if not symbols:
                break

            prices = self._fetch_prices(symbols)
            for symbol, sig in list(self.active_positions.items()):
                if sig.state not in (PositionState.FILLED, PositionState.MONITORING):
                    continue
                sig.state = PositionState.MONITORING

                price = prices.get(symbol, 0)
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



class GapFadePaperTrader(GapFadeAutoTrader):
    """Paper trading on the REAL Capital account - answers "can this run live?".

    Capital's SKCOM has no simulated-order facility. Verified against the
    installed type library (D:\\CapitalAPI\\CapitalAPI_2.13.59_PythonExample\\元件\\x64\\SKCOM.dll):
    ISKOrderLib exposes 155 members and none of them is a paper / try order.
    The second argument of SendStockStrategyDayTrade is bAsyncOrder, not a
    simulation flag - see the official sample
    PythonExampleV2/Order/TS/TSStrategyOrder/TSStrategyOrder.py:792. The only
    sandbox is SKCenterLib_SetAuthority(2) = 測試環境, which is a different server
    with a different account, so it cannot prove THIS account can trade.

    Paper mode therefore keeps every real dependency and removes only the risk:

      1. Real login, real quote feed, real scan / model / sizing - identical to live.
      2. A real 智慧單 per signal, visible in the Capital App, but sized
         paper_probe_zhang 張 at a price that cannot trade: LONG buys at 跌停,
         SHORT sells at 漲停. If it somehow does fill, the 13:20 time-clear
         flattens it, so the worst case is one 張 of one stock for a few hours.
      3. The real ticket (full 張數, real SL/TP) is simulated internally against
         the live quote feed at paper_poll_sec resolution, which yields the P&L,
         win rate and entry-slippability numbers that decide live feasibility.
    """

    def run(self):
        """Refuse to run outside the session: a night run would scan today's stale
        opening prices, get every order rejected, and report a misleading verdict."""
        now = datetime.now()
        start = now.replace(hour=8, minute=55, second=0, microsecond=0)
        stop = now.replace(hour=13, minute=40, second=0, microsecond=0)
        if not (start <= now <= stop):
            print("PAPER MODE needs the live session. Current time "
                  f"{now:%H:%M:%S} is outside 08:55-13:40.")
            print("Run it on a trading day before 09:00 (it waits for the open),")
            print("or use `python gap_fade_auto.py scan` to test the feed only.")
            return 0
        return super().run()

    def connect(self):
        super().connect()
        self.log.info("PAPER MODE - real orders at prices that cannot fill")
        try:
            nCode = self.m_pSKOrder.GetRealBalanceReport(self.user_id, self.account)
            center_code = self.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
            self.log.info(f"  GetRealBalanceReport -> "
                          f"{self.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)}")
            reply = self._wait_for_timeout_free_balance()
            if reply:
                self.exec_stats["account_balance"] = reply["text"]
                self.log.info(f"  account equity reply:\n{reply['text'][:1500]}")
            else:
                self.log.warning("  no balance data within 6s. The reply host is connected "
                                 f"(request returned {center_code}), so this is either a "
                                 "session-hours restriction or a channel this host does not "
                                 "use. Non-blocking: the three feasibility gates do not "
                                 "depend on it.")
        except Exception as e:
            self.log.warning(f"  GetRealBalanceReport failed: {e}")

    def _wait_for_timeout_free_balance(self):
        # The host labels the cash report differently across versions, so match
        # loosely and fall back to whatever arrives.
        for keys in (("現金", "cash", "餘額", "balance"), ("913R", "918D"), ()):
            r = self._wait_for_reply(keys, timeout_sec=2.0)
            if r:
                return r
        return None

    def _wait_for_reply(self, keywords: tuple[str, ...] = (), timeout_sec: float = 6.0):
        """Block until the Reply channel delivers something (optionally matching a
        keyword). Report requests are asynchronous, so without this the balance
        simply never arrives before we disconnect."""
        deadline = time.time() + timeout_sec
        start_r, start_d = len(self._replies), len(self._report_rows)
        while time.time() < deadline:
            for r in self._replies[start_r:]:
                if not keywords or any(k.lower() in r["text"].lower() for k in keywords):
                    return {"ts": r["ts"], "text": r["text"]}
            for d in self._report_rows[start_d:]:
                if d["row"] == "<COMPLETE>":
                    rows = [x["row"] for x in self._report_rows[start_d:] if x["row"] != "<COMPLETE>"]
                    if rows and (not keywords or any(k.lower() in "\n".join(rows).lower() for k in keywords)):
                        return {"ts": d["ts"], "text": "\n".join(rows)}
                if not keywords and d["row"]:
                    return {"ts": d["ts"], "text": d["row"]}
            time.sleep(0.25)
        return None

    def _paper_state_path(self) -> Path:
        p = self.config.equity_state_path
        return p.with_name(p.stem + "_paper.json")

    def _load_equity_state(self):
        """Paper reads only its own state file.

        The drawdown brake is driven by peak/current equity. If a simulated day
        leaked into the file `live` reads, the next live session would start
        already braked. That is the same trap as the sim residue fixed in
        LIVE_READINESS 8.2; paper is just a newer source of it.
        """
        path = self._paper_state_path()
        if not path.exists():
            self.log.info("  no paper equity state - starting from config.capital "
                          f"({self.config.capital:,.0f}); live's "
                          f"{self.config.equity_state_path.name} is not read here")
            return
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            self._peak_equity = state.get("peak_equity", self.config.capital)
            self._current_equity = state.get("current_equity", self.config.capital)
            self.log.info(f"  Loaded PAPER equity state: peak={self._peak_equity:,.0f} "
                          f"current={self._current_equity:,.0f}")
        except Exception as e:
            self.log.warning(f"  paper equity state unreadable: {e}")

    def _save_equity_state(self):
        """Persist to the paper file only - never to the one `live` reads."""
        path = self._paper_state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "peak_equity": self._peak_equity,
                "current_equity": self._current_equity,
                "updated": datetime.now().isoformat(),
                "note": "paper mode - simulated PnL, deliberately NOT used by live",
            }, indent=2), encoding="utf-8")
            self.log.info(f"  equity state -> {path.name} "
                          f"(live's {self.config.equity_state_path.name} untouched)")
        except Exception as e:
            self.log.warning(f"  paper equity state not saved: {e}")

    def _probe_price(self, sig: Signal) -> float:
        """A limit price that cannot trade: 跌停 for a buy, 漲停 for a sell."""
        limit_up, limit_down = calc_price_limits(sig.prev_close)
        return limit_down if sig.direction == Direction.LONG else limit_up

    def _place_entry_order(self, sig: Signal):
        """Send the risk-free probe order, keep the real ticket for simulation."""
        real_entry, real_shares = sig.entry_price, sig.shares
        sig._real_entry = real_entry
        sig._real_shares = real_shares
        sig._slip_measured = False

        probe = self._probe_price(sig)
        self.log.info(
            f"  [PAPER] {sig.symbol} intended ticket: {real_shares:,} shares "
            f"@ {real_entry} SL={sig.sl_price} TP={sig.tp_price} "
            f"-> sending {self.config.paper_probe_zhang} 張 @ {probe} (cannot fill)")
        sig.entry_price = probe
        sig.shares = self.config.paper_probe_zhang * 1000
        super()._place_entry_order(sig)
        # Restore the real ticket so _mark_exit prices the trade we WOULD have done.
        sig.entry_price = real_entry
        sig.shares = real_shares

        # Register the SIMULATED ticket no matter what the probe order did.
        # The probe is priced so it can never fill, and the broker can also
        # reject it outright - on 2026-10-28 every SHORT came back as
        # error 924 "投資人未具有上市/上櫃股票當沖資格(無券當沖)". If registering
        # depended on the probe being accepted, run() would log "No positions
        # entered. Done." and skip the whole simulated session, so paper would
        # produce zero feasibility data on exactly the days that most need
        # explaining. The rejection is still counted honestly: the
        # submit-acceptance gate reads exec_stats["orders"], which the parent
        # already filled with ack_code / msg.
        if sig.state == PositionState.CANCELLED:
            rec = next((r for r in reversed(self.exec_stats.get("orders", []))
                        if r["symbol"] == sig.symbol), None) or {}
            why = str(rec.get("broker_msg") or rec.get("msg", ""))
            self.log.info(f"  [PAPER] {sig.symbol} probe rejected "
                          f"code={rec.get('ack_code')} {why[:150]}")
            self.log.info(f"  [PAPER] {sig.symbol} simulating the intended ticket "
                          f"anyway; the rejection is counted as a submit failure")
            sig.state = PositionState.FILLED
        self.active_positions[sig.symbol] = sig

    def _measure_entry_slippage(self, prices: dict):
        """First observable price vs the intended entry - the number the backtest
        cannot know. Positive = worse than the backtest entry."""
        # The timestamp is part of the measurement: a value taken minutes after
        # the open describes a late start, not the live path.
        t_obs = time.time()
        for sym, price in prices.items():
            sig = self.active_positions.get(sym)
            if sig is None or getattr(sig, "_slip_measured", True):
                continue
            if not price or not getattr(sig, "_real_entry", 0):
                continue
            sig._slip_measured = True
            raw = (price - sig._real_entry) / sig._real_entry
            adverse = raw if sig.direction == Direction.LONG else -raw
            self.exec_stats.setdefault("entry_slippage", []).append(
                {"symbol": sym, "intended": sig._real_entry, "observed": price,
                 "adverse_pct": adverse * 100,
                 "after_open_sec": t_obs - self.exec_stats.get("t_open", t_obs)})
            self.log.info(f"  [PAPER] {sym} entry check: intended {sig._real_entry} "
                          f"vs first price {price} -> adverse {adverse*100:+.2f}%")

    def monitor_positions(self):
        """Simulated fills driven by the real quote feed."""
        from datetime import timedelta
        self.log.info("=" * 60)
        self.log.info("STEP 3: PAPER monitoring - real quotes, simulated fills")
        poll = self.config.paper_poll_sec
        force_dt = self._parse_time(self.config.force_exit_time)
        end_dt = force_dt + timedelta(minutes=5)
        first_poll = True
        # Between exits this session is silent, and these logs are what gets
        # reviewed afterwards to decide whether live behaved as modelled. A
        # heartbeat makes "is it still polling, and how fast did a round take"
        # answerable from the log alone instead of inferred from the process
        # still existing.
        heartbeat_sec = 300.0
        next_beat = time.time() + heartbeat_sec

        while self.running:
            now = datetime.now()
            if now >= end_dt:
                self.log.info("  Session window over.")
                break
            open_sigs = [sig for sig in self.active_positions.values()
                         if sig.state in (PositionState.FILLED, PositionState.MONITORING)]
            if not open_sigs:
                self.log.info("  All paper positions resolved.")
                break

            t_fetch = time.time()
            prices = self._fetch_prices([sig.symbol for sig in open_sigs])
            fetch_sec = time.time() - t_fetch
            # A session that began after 09:00 cannot know WHEN a level was
            # crossed. Settling such a position at the observed price invents a
            # fill that never happened, so it is settled at the level instead and
            # tagged PRESTART to keep it out of any comparison with the backtest.
            late_start = first_poll and (
                time.time() - self.exec_stats.get("t_open", time.time())) > 60
            if first_poll:
                self._measure_entry_slippage(prices)
                first_poll = False

            if time.time() >= next_beat:
                next_beat = time.time() + heartbeat_sec
                self.log.info(f"  [PAPER HEARTBEAT] {now:%H:%M:%S} "
                              f"open={len(open_sigs)} round_trip={fetch_sec*1000:.0f}ms")
                for sig in open_sigs:
                    px = prices.get(sig.symbol)
                    if not px:
                        self.log.info(f"      {sig.symbol}: no quote this round")
                        continue
                    if sig.direction == Direction.SHORT:
                        to_sl = (sig.sl_price - px) / px * 100
                        to_tp = (sig.tp_price - px) / px * 100
                    else:
                        to_sl = (px - sig.sl_price) / px * 100
                        to_tp = (px - sig.tp_price) / px * 100
                    self.log.info(
                        f"      {sig.symbol} {sig.direction.value} px={px} "
                        f"entry={sig.entry_price} SL={sig.sl_price}({to_sl:+.2f}%) "
                        f"TP={sig.tp_price}({to_tp:+.2f}%)")

            force = now >= force_dt
            for sig in open_sigs:
                price = prices.get(sig.symbol)
                if not price:
                    continue
                if force:
                    self._mark_exit(sig, price, "FORCE_CLOSE")
                    continue
                if sig.direction == Direction.SHORT:
                    hit_sl, hit_tp = price >= sig.sl_price, price <= sig.tp_price
                else:
                    hit_sl, hit_tp = price <= sig.sl_price, price >= sig.tp_price
                # A poll that crosses both levels takes the stop: the intra-poll
                # order is unknown, so assume the worse outcome.
                if hit_sl:
                    if late_start:
                        self._mark_exit(sig, sig.sl_price, "STOP_LOSS_PRESTART")
                    else:
                        self._mark_exit(sig, price, "STOP_LOSS")
                elif hit_tp:
                    if late_start:
                        self._mark_exit(sig, sig.tp_price, "TAKE_PROFIT_PRESTART")
                    else:
                        self._mark_exit(sig, price, "TAKE_PROFIT")
            time.sleep(poll)

    def daily_report(self):
        super().daily_report()
        self._paper_report()

    def _paper_report(self):
        import statistics as st
        self.log.info("=" * 60)
        self.log.info("LIVE FEASIBILITY REPORT (paper)")

        acks = [o["ack_latency"] for o in self.exec_stats.get("orders", [])
                if o.get("ack_latency")]
        codes = [o.get("ack_code") for o in self.exec_stats.get("orders", [])]
        rejected = [o for o in self.exec_stats.get("orders", []) if o.get("ack_code") != 0]
        slips = [x["adverse_pct"] for x in self.exec_stats.get("entry_slippage", [])]
        trades = self.closed_trades

        def pct(v, q):
            return st.quantiles(v, n=100)[min(99, int(q * 100) - 1)] if len(v) >= 20 else (max(v) if v else 0.0)

        checks = []
        self.log.info(f"  Orders sent: {len(codes)} | accepted: {len(codes)-len(rejected)} "
                      f"| rejected: {len(rejected)}")
        for o in rejected:
            why = str(o.get("broker_msg") or o.get("msg", ""))
            self.log.info(f"    REJECT {o['symbol']}: code={o['ack_code']} {why[:120]}")
        # Rejections that repeat with the SAME broker reason are an account
        # qualification problem, not a per-order glitch. Name the fix instead of
        # making the user diff 7 identical lines.
        blockers = []
        if rejected:
            groups = {}
            for o in rejected:
                key = str(o.get("broker_msg") or o.get("msg", ""))[:90].strip()
                groups[key] = groups.get(key, 0) + 1
            for key, n in sorted(groups.items(), key=lambda kv: -kv[1]):
                if n < 2:
                    continue
                self.log.warning(f"  SYSTEMIC: {n}/{len(codes)} orders rejected for the "
                                 f"same reason: {key}")
                if "當沖資格" in key:
                    side = "無券當沖(放空)" if any(
                        o.get("direction") == "SHORT" for o in rejected) else "當沖"
                    self.log.warning(
                        f"    -> the account does not hold the broker's {side} "
                        "qualification. This is granted by application and 上市 / "
                        "上櫃 are approved separately, so one can work while the "
                        "other does not. Until it is on, every affected signal is "
                        "untradeable no matter what the model says.")
                    blockers.append(f"broker qualification missing: {key}")
                else:
                    blockers.append(f"systemic order rejection x{n}: {key}")
        checks.append(("order acceptance 100%", not rejected and bool(codes)))

        if acks:
            self.log.info(f"  submit->ack: p50 {st.median(acks)*1000:.0f}ms "
                          f"p90 {pct(acks,0.9)*1000:.0f}ms max {max(acks)*1000:.0f}ms")
            checks.append(("ack p90 < 2000ms", pct(acks, 0.9) < 2.0))
        else:
            checks.append(("ack measured", False))

        # The gate used to be "adverse p90 < 0.5 pct", which is WRONG and would
        # have failed every normal day: measured on 2026 1-minute data the
        # opening price is readable at p50 +10s and acting then costs +0.098 pct
        # adverse on average with p90 +1.408 pct (11,157 shorts). That is the
        # normal case, not a failure. What matters is the cost RELATIVE to the
        # edge. Measured relationship: the raw adverse overstates the damage to
        # the whole trade by ~2.5x (raw +0.098 pct becomes a net -0.039 pp on
        # the trade, because the exit shifts with the entry), and the edge on
        # the trades the strategy actually takes is 0.382 pct/trade. So the
        # honest gate is: net cost < 25 pct of the edge.
        EDGE_PER_TRADE = 0.382      # pct, measured 2026, top-10 signals per day
        NET_FROM_RAW = 0.40         # net trade cost / raw adverse entry slippage
        delays = [x.get("after_open_sec") for x in self.exec_stats.get("entry_slippage", [])
                  if x.get("after_open_sec") is not None]
        late_start = bool(delays) and st.median(delays) > 60
        if slips and late_start:
            self.log.warning(
                f"  entry slippability: NOT TESTED under live conditions. This "
                f"process first read prices {st.median(delays):.0f}s after "
                f"09:00:00, so the {len(slips)} readings below (mean adverse "
                f"{st.mean(slips):+.2f}%) measure a late start, not the live path. "
                f"Start before 09:00 to measure the real thing.")
            checks.append(("entry slippable [NOT TESTED - started after the open]", False))
            blockers.append(
                f"slippage unmeasurable: first price read {st.median(delays):.0f}s "
                f"after 09:00")
        elif slips:
            adverse = [x for x in slips if x > 0]
            mean_adv = st.mean(slips)
            net = mean_adv * NET_FROM_RAW
            share = net / EDGE_PER_TRADE * 100
            self.log.info(f"  entry slippability: n={len(slips)} | adverse p50 "
                          f"{st.median(slips):+.2f}% p90 {pct(slips,0.9):+.2f}% | "
                          f"filled worse than intended: {len(adverse)}/{len(slips)}")
            self.log.info(f"  implied net cost on the trade ~{net:.3f}% "
                          f"({NET_FROM_RAW:.2f} x raw adverse, measured relationship) "
                          f"= {share:.0f}% of the {EDGE_PER_TRADE:.3f}% per-trade edge")
            self.log.info("    baseline from 2026 1-minute data: mean +0.098%, "
                          "p90 +1.408% -> a day near that is NORMAL, not a failure")
            checks.append((f"delay cost < 25% of the per-trade edge "
                           f"(raw adverse mean < {0.25*EDGE_PER_TRADE/NET_FROM_RAW:.3f}%)",
                           mean_adv < 0.25 * EDGE_PER_TRADE / NET_FROM_RAW))
        else:
            self.log.info("  entry slippability: not measured (no positions)")
            checks.append(("entry slippable", False))

        if trades:
            pnls = [t.get("pnl", 0.0) for t in trades]
            wins = sum(1 for x in pnls if x > 0)
            self.log.info(f"  simulated book: {len(trades)} trades | win rate "
                          f"{wins/len(trades)*100:.1f}% | total PnL {sum(pnls):+,.0f} "
                          f"(cost included) | avg {st.mean(pnls):+,.0f}")
            by_reason = {}
            for t in trades:
                by_reason[t.get("reason", "?")] = by_reason.get(t.get("reason", "?"), 0) + 1
            self.log.info(f"  exit reasons: {by_reason}")
            prestart = [t for t in trades if t.get("reason", "").endswith("_PRESTART")]
            if prestart:
                self.log.warning(
                    f"  {len(prestart)} of these were already through a level before "
                    f"this process started observing. They are settled at the level "
                    f"price and tagged _PRESTART - exclude them when comparing with "
                    f"the backtest; a run started before 09:00 has none.")
        else:
            self.log.info("  simulated book: no trades today")

        ok = all(v for _, v in checks)
        for name, passed in checks:
            self.log.info(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        self.log.info(f"  VERDICT: {'live-ready' if ok else 'NOT live-ready'}")

        out = Path(self.config.log_dir) / f"paper_report_{datetime.now():%Y%m%d}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "date": datetime.now().isoformat(),
            "orders": self.exec_stats.get("orders", []),
            "entry_slippage": self.exec_stats.get("entry_slippage", []),
            "trades": trades,
            "checks": {k: bool(v) for k, v in checks},
            "blockers": blockers,
            "verdict": "live-ready" if ok else "not-live-ready",
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        self.log.info(f"  wrote {out}")


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
    elif mode == "paper":
        print("PAPER MODE - real Capital account, risk-free orders + simulated fills")
        print(f"  Account: {config.cust_cert_id} | Capital: {config.capital:,.0f}")
        print("  Orders ARE sent and visible in the Capital App, but 1 張 at a price")
        print("  that cannot trade (跌停 for buys, 漲停 for sells). The real ticket is")
        print("  simulated against the live quote feed. Capital has no paper-order API.")
        trader = GapFadePaperTrader(config)
    elif mode == "scan":
        print("SCAN / RISK1 - full-market quote scan only, NO orders")
        print("  Polls until 09:01:00 and reports when opening prices actually")
        print("  become visible, and what the exchange says the opening print time was.")
        trader = GapFadeSimulator(config)
        trader.connect()
        codes = trader._load_stock_list()
        print(f"  Universe: {len(codes)} codes")

        import datetime as _dt
        today_s = _dt.date.today().isoformat()
        open_dt = _dt.datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
        stop_at = open_dt + _dt.timedelta(seconds=60)
        if _dt.datetime.now() >= stop_at:
            stop_at = _dt.datetime.now() + _dt.timedelta(seconds=6)

        first_visible = None
        earliest_open = {}
        dated = 0
        trial = 0
        while True:
            trial += 1
            t0 = time.time()
            rows, source = trader._batch_scan(codes)
            took = time.time() - t0
            named = [r for r in rows if r.get("n")]
            by_ex = {}
            for r in named:
                by_ex[r.get("x") or "?"] = by_ex.get(r.get("x") or "?", 0) + 1
            dated = sum(1 for r in named if str(r.get("d")) == today_s)
            with_open = sum(1 for r in named if _to_float(r.get("o")) > 0)
            with_ot = 0
            for r in named:
                ot = _to_float(r.get("ot"))
                if ot > 0:
                    with_ot += 1
                    earliest_open.setdefault(r["c"], ot)
            if with_ot and first_visible is None:
                first_visible = t0
            print("  poll#%d %s via %s: rows=%d feed_today=%d has_open=%d "
                  "has_openTime=%d by_exchange=%s %.2fs"
                  % (trial, _dt.datetime.now().strftime("%H:%M:%S"), source,
                     len(named), dated, with_open, with_ot, by_ex, took))
            if _dt.datetime.now() >= stop_at:
                break
            time.sleep(2)

        # The summary goes through the logger, not print(), so it lands in
        # trading_logs/ and becomes a durable "RISK1 measured" marker - the
        # 08:55 reminder checks for this line before nagging again.
        log = trader.log
        log.info("=" * 60)
        if dated:
            log.info(f"  FEED IS LIVE for {today_s} ({dated} codes on this session)")
        else:
            log.info(f"  FEED IS NOT ON {today_s} - the exchange has no session "
                     f"for today. RISK1 cannot be measured; run this again on a "
                     f"trading day.")
        if not dated:
            # The feed answers with the LAST trading session when today is
            # closed, so openTime would be days old and the percentiles below
            # would be large negatives. Refuse to report a made-up number.
            log.info("  RISK1: not measured (no live session today).")
        elif earliest_open:
            lats = sorted(v / 1_000_000.0 - open_dt.timestamp()
                          for v in earliest_open.values())
            n = len(lats)
            q = lambda p: lats[min(n - 1, int(p * n))]
            log.info(f"  RISK1 exchange opening-print time, seconds after "
                     f"09:00:00 (n={n}):")
            log.info(f"    p50={q(0.5):.2f}s  p90={q(0.9):.2f}s  "
                     f"p99={q(0.99):.2f}s  max={lats[-1]:.2f}s")
            if first_visible and first_visible - open_dt.timestamp() <= 120:
                log.info(f"  RISK1 first openPrice we could read: "
                         f"{first_visible - open_dt.timestamp():.2f}s after "
                         f"09:00:00")
            else:
                # Running after the close, first_visible is "hours ago" and the
                # number means nothing. The exchange-side percentiles above DO
                # still apply - they come from the feed's own open timestamp for
                # today's session, not from when this process happened to poll.
                log.info("  RISK1 our-own first readable price: not measured "
                         "(this run did not straddle 09:00). The percentiles "
                         "above are the feed's open timestamps for today's "
                         "session and remain valid.")
        else:
            log.info("  RISK1: feed is live but carries no openTime field "
                     "(TWSE MIS fallback). Re-run when Fugle answers.")
        sys.exit(0)
    elif mode == "now":
        print("NOW MODE - Immediate execution (no time wait, 30min monitor)")
        print(f"  Capital: {config.capital:,.0f}")
        trader = GapFadeNowTrader(config)
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python gap_fade_auto.py [live|paper|sim|scan|now]")
        print("  paper = real Capital account, risk-free probe orders + simulated")
        print("          fills; the mode that answers 'can this run live?'")
        print("  scan  = full-market quote scan + RISK1 opening-print timing only")
        sys.exit(1)

    trader.run()
