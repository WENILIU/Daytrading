"""Rehearsal: run the WHOLE paper chain on today's real data, with only the
exchange submission stubbed.

Why this exists: Capital's SKCOM has no paper-order API, so the only way to test
order acceptance is to send real orders during a session. That test can only run
at 09:00 on a trading day. Everything else in the chain can be tested now:

    real quote feed -> real scan -> real filters -> v13 model -> real sizing
    -> real STOCKSTRATEGYORDER struct -> [STUB] exchange

So a rehearsal answers "does the chain produce the tickets we think it does", and
leaves exactly one unknown: does the exchange accept them. The report says so.

Exit prices come from today's real day high/low/close, so the SL/TP hit ORDER
inside the day is unknown; the stop is assumed first (same conservative rule the
live monitor uses when one poll crosses both levels). P&L here is therefore an
estimate, not a measured result.

Usage:  python paper_rehearsal.py            # today
"""
import sys, json, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, ".")
from gap_fade_auto import (Config, GapFadePaperTrader, Direction, PositionState,
                           Signal, calc_price_limits, sk)


class StubOrderLib:
    """Stands in for ISKOrderLib. Records the real struct, returns success."""

    def __init__(self, owner):
        self.owner = owner

    def SendStockStrategyDayTrade(self, user_id, bAsyncOrder, oOrder):
        rec = {
            "account": oOrder.bstrFullAccount, "stock": oOrder.bstrStockNo,
            "zhang": oOrder.nQty, "price": oOrder.bstrOrderPrice,
            "buy_sell": oOrder.nBuySell,
            "sl_flag": oOrder.nStopLossFlag, "sl_trigger": oOrder.bstrSLTrigger,
            "sl_pct_mode": oOrder.nRDOSLPercent, "sl_market_after": oOrder.nRDSLMarketPriceType,
            "tp_flag": oOrder.nTakeProfitFlag, "tp_trigger": oOrder.bstrTPTrigger,
            "tp_pct_mode": oOrder.nRDOTPPercent,
            "clear_flag": oOrder.nClearAllFlag, "clear_time": oOrder.bstrClearCancelTime,
            "clear_market": oOrder.nClearAllPriceType,
            "async_flag": bAsyncOrder,
        }
        self.owner.exec_stats.setdefault("structs", []).append(rec)
        return (f"REHEARSAL-{len(self.owner.exec_stats['structs'])}", 0)

    def GetRealBalanceReport(self, user_id, account):
        return 0


class StubCenterLib:
    def SKCenterLib_GetReturnCodeMessage(self, code):
        return f"REHEARSAL-STUB(code={code})"


class RehearsalTrader(GapFadePaperTrader):
    """Paper chain, exchange stubbed, no clock waits."""

    def connect(self):
        self.log.info("REHEARSAL MODE - real feed/scan/model/sizing/order-struct, "
                      "exchange submission STUBBED")
        self.yahoo.connect()
        self._logged_in = True
        # live connect() auto-detects this; hard-coded here only so the stub
        # struct shows a realistic account field.
        self.account = "913R0438724"
        self.m_pSKOrder = StubOrderLib(self)
        self.m_pSKCenter = StubCenterLib()

    def disconnect(self):
        pass

    def _wait_until(self, time_str):
        pass

    def _wait_for_quotes(self, *a, **k):
        pass

    def run(self):
        self.running = True
        self.log.info("=" * 60)
        self.log.info("GAP FADE v13 REHEARSAL (no orders reach the exchange)")
        self.log.info(f"Capital: {self.config.capital:,.0f}")
        self.log.info(f"Time: {datetime.now().isoformat()}")
        try:
            self.connect()
            self.exec_stats["t_open"] = self._parse_time("09:00").timestamp()
            self.scan_signals()
            self.exec_stats["t_scan_done"] = time.time()
            if not self.signals:
                self.log.info("No signals today. The chain still ran end-to-end.")
                self._rehearsal_report()
                return
            self.confirm_and_enter()
            self._resolve_exits_from_today()
            self._rehearsal_report()
        except Exception as e:
            self.log.error(f"FATAL: {e}", exc_info=True)
        finally:
            self.running = False
            self.disconnect()

    # ---- exit resolution from today's real session extremes ----
    def _today_ohlc(self, codes):
        out = {}
        for i in range(0, len(codes), 50):
            for q in self.yahoo._fetch_batch(codes[i:i + 50]):
                sym = str(q.get("symbol", "")).replace(".TW", "")
                out[sym] = {
                    "open": q.get("regularMarketOpen") or q.get("regularMarketPrice") or 0,
                    "high": q.get("regularMarketDayHigh") or 0,
                    "low": q.get("regularMarketDayLow") or 0,
                    "close": q.get("regularMarketPrice") or 0,
                }
        # Yahoo drops some small / recently-changed names. Fall back to the same
        # Fugle feed the live monitor uses, so the rehearsal does not quietly
        # invent a flat day for a name we simply could not price.
        missing = [c for c in codes if not out.get(c, {}).get("close")]
        if missing:
            try:
                px = self._fetch_prices(missing)
                for c, p in px.items():
                    if p and p > 0:
                        out.setdefault(c, {})["close"] = p
                        out[c]["source"] = "fugle_close_only"
            except Exception as e:
                self.log.warning(f"  Fugle fallback failed: {e}")
        return out

    def _resolve_exits_from_today(self):
        open_sigs = [s for s in self.active_positions.values()
                     if s.state in (PositionState.FILLED, PositionState.MONITORING)]
        if not open_sigs:
            return
        ohlc = self._today_ohlc([s.symbol for s in open_sigs])
        L = self.log
        L.info("=" * 60)
        L.info("REHEARSAL exit resolution - today's real OHLC, stop assumed first")
        L.info("  (no 1-minute data for today, so the intraday SL/TP ORDER is unknown;")
        L.info("   assuming the stop is the worse outcome, same rule as the live monitor)")
        for sig in open_sigs:
            bar = ohlc.get(sig.symbol) or {}
            hi, lo, cl = bar.get("high", 0), bar.get("low", 0), bar.get("close", 0)
            sig._today_ohlc = bar
            lu, ld = calc_price_limits(sig.prev_close)
            bar["limit_up"], bar["limit_down"] = lu, ld
            if not cl:
                self._mark_exit(sig, sig.entry_price, "NO_DATA")
                continue
            if not hi or not lo:
                # close only: cannot tell whether SL/TP was touched intraday
                self._mark_exit(sig, cl, "FORCE_CLOSE_1320_close_only")
                continue
            if sig.direction == Direction.SHORT:
                hit_sl, hit_tp = hi >= sig.sl_price, lo <= sig.tp_price
                px = sig.sl_price if hit_sl else (sig.tp_price if hit_tp else cl)
                pinned = hit_sl and hi >= lu
            else:
                hit_sl, hit_tp = lo <= sig.sl_price, hi >= sig.tp_price
                px = sig.sl_price if hit_sl else (sig.tp_price if hit_tp else cl)
                pinned = hit_sl and lo <= ld
            reason = "STOP_LOSS" if hit_sl else ("TAKE_PROFIT" if hit_tp else "FORCE_CLOSE_1320")
            self._mark_exit(sig, px, reason)
            if pinned:
                # The stop sits at 漲停 - 1 tick. If the name is PINNED at the
                # limit, the stop's market order fills AT the limit, one tick
                # worse than the backtest price. Charge it here so the number
                # in front of the user is the one they will actually get.
                worse = lu if sig.direction == Direction.SHORT else ld
                gap = abs(worse - sig.sl_price) * sig.shares
                sig.pnl -= gap
                for t in self.closed_trades:
                    if t["symbol"] == sig.symbol:
                        t["pnl"] = sig.pnl
                        t["limit_pinned_tick_cost"] = round(gap, 0)
                L.info(f"    ^ {sig.symbol} stopped while pinned at the limit: fill "
                       f"{worse} not {sig.sl_price}, extra cost {gap:,.0f}")

    def _rehearsal_report(self):
        L = self.log
        L.info("=" * 60)
        L.info("REHEARSAL REPORT - NOT a live-readiness verdict")
        L.info("  The three feasibility gates (order acceptance / ack latency /")
        L.info("  entry slippage) need a real session and are NOT tested here.")

        structs = self.exec_stats.get("structs", [])
        orders = self.exec_stats.get("orders", [])
        by_sym = {s.symbol: s for s in self.signals}
        L.info(f"  signals produced: {len(self.signals)}")
        L.info(f"  orders built    : {len(orders)}  (structs assembled: {len(structs)})")

        L.info("")
        L.info("  REAL ticket the strategy sized (this is what live would place):")
        L.info(f"    {'stock':<7}{'dir':<6}{'zhang':>6}{'entry':>9}{'SL':>9}{'TP':>9}"
               f"{'notional':>12}{'pos%':>7}{'maxloss':>10}  {'zt%':>5} {'adjgap%':>7}")
        tot_notional = 0.0
        for o in orders:
            sig = by_sym.get(o["symbol"])
            if sig is None:
                continue
            zhang = max(1, int(sig.shares) // 1000)
            notional = zhang * 1000 * sig.entry_price
            tot_notional += notional
            ml = abs(sig.sl_price - sig.entry_price) * sig.shares
            L.info(f"    {sig.symbol:<7}{sig.direction.value:<6}{zhang:>6}{sig.entry_price:>9}"
                   f"{sig.sl_price:>9}{sig.tp_price:>9}{notional:>12,.0f}"
                   f"{sig.entry_price * sig.shares / self.config.capital * 100:>6.1f}%"
                   f"{ml:>10,.0f}  {sig.zt_dist * 100:>5.2f} {sig.adj_gap * 100:>7.2f}")
        L.info(f"    total notional {tot_notional:,.0f} = "
               f"{tot_notional / self.config.capital * 100:.0f}% of capital (zero margin)")

        L.info("")
        L.info("  PROBE order actually sent to the exchange (1 zhang, cannot fill):")
        for o, st in zip(orders, structs):
            sig = by_sym.get(o["symbol"])
            probe = self._probe_price(sig) if sig else 0
            ok = (st["sl_flag"] == 1 and st["tp_flag"] == 1 and st["clear_flag"] == 1
                  and st["clear_time"] == "1320" and st["sl_pct_mode"] == 0
                  and st["tp_pct_mode"] == 0 and st["sl_market_after"] == 1
                  and st["clear_market"] == 1 and st["zhang"] == 1)
            L.info(f"    {o['symbol']:<7}{'SELL' if st['buy_sell'] == 1 else 'BUY ':<6}"
                   f"{st['zhang']:>3} 張 @ {probe:<9} SL={st['sl_trigger']:<9}"
                   f"TP={st['tp_trigger']:<9} clear={st['clear_time']}  {'OK' if ok else 'BAD'}")
        bad = [st for st in structs
               if not (st["sl_flag"] == 1 and st["tp_flag"] == 1 and st["clear_flag"] == 1
                       and st["clear_time"] == "1320" and st["zhang"] == 1)]
        L.info(f"  struct field check: {len(structs) - len(bad)}/{len(structs)} carry a valid "
               f"SL + TP + 13:20 market time-clear, sized 1 zhang")

        trades = self.closed_trades
        if trades:
            pnls = [t.get("pnl", 0.0) for t in trades]
            wins = sum(1 for x in pnls if x > 0)
            reasons = {}
            for t in trades:
                reasons[t.get("reason", "?")] = reasons.get(t.get("reason", "?"), 0) + 1
            L.info("")
            L.info("  estimated book (day-OHLC, stop-first, limit-pinned tick cost charged):")
            full = [t for t in trades if t.get("reason") != "FORCE_CLOSE_1320_close_only"]
            approx = [t for t in trades if t.get("reason") == "FORCE_CLOSE_1320_close_only"]
            for label, grp in (("  resolvable (full OHLC)", full),
                               ("  close-only, intraday SL/TP unknown", approx)):
                if not grp:
                    continue
                g = [t.get("pnl", 0.0) for t in grp]
                w = sum(1 for x in g if x > 0)
                L.info(f"  {label}: {len(grp)} trades | win {w/len(grp)*100:.0f}% | "
                       f"PnL {sum(g):+,.0f} ({sum(g)/self.config.capital*100:+.2f}% of capital)")
            L.info(f"    total {len(trades)} trades | PnL {sum(pnls):+,.0f} "
                   f"({sum(pnls)/self.config.capital*100:+.2f}% of capital) | reasons {reasons}")
            if trades and len(trades) - len(full):
                L.info(f"    {len(trades)-len(full)} of {len(trades)} could not be priced "
                       f"intraday - do NOT read the total as a measured result")
            pinned = [t for t in trades if t.get("limit_pinned_tick_cost")]
            if pinned:
                L.info(f"    {len(pinned)} stop(s) were pinned at the price limit - "
                       f"the backtest price is 1 tick optimistic on those")
            L.info("    ^ ESTIMATE. Intraday hit order is unknown without 1-minute data.")

        for name in ("order acceptance", "submit->ack latency", "entry slippage"):
            L.info(f"  [NOT TESTED] {name} - requires a live session")
        L.info("  VERDICT: chain verified end-to-end up to the exchange. "
               "Run `python gap_fade_auto.py paper` during a session for the verdict.")

        out = Path(self.config.log_dir) / f"rehearsal_{datetime.now():%Y%m%d}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "mode": "rehearsal",
            "note": "exchange submission stubbed; not a live-readiness test",
            "date": datetime.now().isoformat(),
            "signals": [{"symbol": s.symbol, "direction": s.direction.value,
                         "raw_gap": round(s.raw_gap, 4), "adj_gap": round(s.adj_gap, 4),
                         "entry": s.entry_price, "sl": s.sl_price, "tp": s.tp_price,
                         "shares": s.shares, "tier": s.tier,
                         "pred": round(s.pred, 5), "pred_q": round(s.pred_q, 4),
                         "q1": round(s.q1, 4), "zt_dist": round(s.zt_dist, 4),
                         "prev_turnover": s.prev_turnover,
                         "today_ohlc": getattr(s, "_today_ohlc", None)}
                        for s in self.signals],
            "orders": orders,
            "structs": structs,
            "trades": trades,
            "gates_tested": False,
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        L.info(f"  wrote {out}")


if __name__ == "__main__":
    t = RehearsalTrader(Config())
    t.run()
