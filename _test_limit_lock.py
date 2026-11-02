# -*- coding: utf-8 -*-
r"""The limit-lock rule: which stops get armed, and what happens when one is not.

Two rules for the case where the PRICE LIMIT, not the 4 pct, is what sets the
stop. "stop" is what has always shipped. "hold" arms no stop leg and lets the
13:25 force close be the exit.

"hold" is not extra risk. A buy order one tick under a locked limit-up sits
behind the queue and does not fill, so for the 52% of these that are still
pinned at 13:25 (1-minute bars, measured 2026-11-02) the "stop" price was never
an obtainable price. "hold" settles those at the limit itself - one tick worse,
and it never pretends a fill happened at a price with no seller behind it.

What must not change under either rule: an ordinary 4 pct stop. That is a price
the market trades through, so it stays armed. The switch only ever touches
limit-bound stops, and the first assertion below is the one that keeps it honest.
"""
import sys, time, logging, types, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(f"  [{'OK  ' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {detail}"))


# ---------- 1. which stop binds ----------
# prev_close 500 -> limit_up 550.0 (tick 1.0), limit_down 450.0 (tick 0.5)
lu, ld = G.calc_price_limits(500.0)
check("limits from 500", (lu, ld) == (550.0, 450.0), f"{lu}/{ld}")

p, pct, bound = G.calc_effective_sl(540.0, 500.0, G.Direction.SHORT, 0.04)
check("SHORT near the limit is limit-bound", bound and p == 549.0, f"{p} {bound}")
p, pct, bound = G.calc_effective_sl(510.0, 500.0, G.Direction.SHORT, 0.04)
check("SHORT far from the limit is an ordinary 4% stop", (not bound) and p == 530.0, f"{p} {bound}")
p, pct, bound = G.calc_effective_sl(460.0, 500.0, G.Direction.LONG, 0.04)
check("LONG near the limit is limit-bound", bound and p == 450.5, f"{p} {bound}")
p, pct, bound = G.calc_effective_sl(490.0, 500.0, G.Direction.LONG, 0.04)
check("LONG far from the limit is an ordinary 4% stop", (not bound) and p == 470.5, f"{p} {bound}")

# the bound flag must be computed the way the backtest computes it after the
# 2026-11-02 label fix: the LIMIT against the SNAPPED normal stop
from v13_engine import snap_price
for entry, direction in ((540.0, G.Direction.SHORT), (510.0, G.Direction.SHORT),
                         (460.0, G.Direction.LONG), (490.0, G.Direction.LONG)):
    _, _, bound = G.calc_effective_sl(entry, 500.0, direction, 0.04)
    if direction == G.Direction.SHORT:
        want = round(lu - 1.0, 2) < snap_price(entry * 1.04)
    else:
        want = round(ld + 0.5, 2) > snap_price(entry * 0.96)
    check(f"bound flag matches the backtest at {entry} {direction.value}", bound == want,
          f"live={bound} backtest={want}")


# ---------- 2. the order legs ----------
class FakeSK:
    def STOCKSTRATEGYORDER(self):
        return types.SimpleNamespace()


def place(rule, entry, direction, use_sl=True, send_probe=True):
    t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
    t.config = G.Config()
    # the probe order is what makes an order object exist to read back; the
    # shipped default is off, so this suite asks for it explicitly unless a
    # case below is specifically about the off path
    t.config.paper_send_probe_orders = send_probe
    t.config.limit_lock_rule = rule
    t.config.use_stop_loss = use_sl
    lg = logging.getLogger("o" + str(abs(hash((rule, entry, str(direction))))))
    lg.handlers = [logging.NullHandler()]
    t.log = lg
    t.account = "3105-00"
    t.user_id = "u"
    t.exec_stats = {}
    t.active_positions = {}
    t.closed_trades = []
    sent = {}

    class OrderLib:
        def SendStockStrategyDayTrade(self, uid, x, o):
            sent["o"] = o
            return ("K|1", 0)
    t.m_pSKOrder = OrderLib()
    t.m_pSKCenter = None

    old_sk = G.sk
    G.sk = FakeSK()
    try:
        sig = G.Signal(symbol="2345", name="t", direction=direction, open_price=entry,
                       prev_close=500.0, raw_gap=0.05, adj_gap=0.05)
        sig.entry_price, sig.shares = entry, 1000
        sig.tier = "T1"
        price, pct, bound = G.calc_effective_sl(entry, 500.0, direction, 0.04)
        sig._sl_pct = pct
        sig._no_stop_leg = bool(not use_sl or (bound and rule == "hold"))
        sig.sl_price = 0.0 if sig._no_stop_leg else price
        sig.tp_price = G.snap_to_valid_price(entry * (1 - 0.12)) if direction == G.Direction.SHORT \
            else G.snap_to_valid_price(entry * (1 + 0.12))
        sig.state = G.PositionState.PENDING
        t._place_entry_order(sig)
    finally:
        G.sk = old_sk
    return sent.get("o"), sig, t


o, sig, t = place("hold", 540.0, G.Direction.SHORT)
check("hold + limit-bound: no stop leg", o is not None and o.nStopLossFlag == 0 and o.bstrSLTrigger == "0",
      o and (o.nStopLossFlag, o.bstrSLTrigger))
check("hold + limit-bound: TP and time clear still armed",
      o.nTakeProfitFlag == 1 and o.nClearAllFlag == 1 and o.bstrClearCancelTime == "1320")
check("hold + limit-bound: the position is still tracked, so 13:25 can close it",
      sig.state == G.PositionState.FILLED and "2345" in t.active_positions)

o, sig, t = place("stop", 540.0, G.Direction.SHORT)
check("stop + limit-bound: stop leg at 漲停-1 tick", o.nStopLossFlag == 1 and o.bstrSLTrigger == "549.0",
      (o.nStopLossFlag, o.bstrSLTrigger))

for rule in ("stop", "hold"):
    o, sig, _t = place(rule, 510.0, G.Direction.SHORT)
    check(f"{rule}: an ordinary 4% stop stays armed regardless",
          o.nStopLossFlag == 1 and o.bstrSLTrigger == "530.0", (o.nStopLossFlag, o.bstrSLTrigger))

check("the shipped default is unchanged", G.Config().limit_lock_rule == "stop"
      and G.Config().use_stop_loss is True,
      (G.Config().limit_lock_rule, G.Config().use_stop_loss))

# use_stop_loss=False is the same mechanism as "hold", applied to every
# position - so an ordinary 4% stop must also go unarmed, and the take profit
# and the time clear must survive, because they are then the only exits.
o, sig, _t = place("stop", 510.0, G.Direction.SHORT, use_sl=False)
check("use_stop_loss=False unarms an ordinary 4% stop too",
      o.nStopLossFlag == 0 and o.bstrSLTrigger == "0", (o.nStopLossFlag, o.bstrSLTrigger))
check("use_stop_loss=False keeps the take profit and the 13:20 clear",
      o.nTakeProfitFlag == 1 and o.nClearAllFlag == 1 and o.bstrClearCancelTime == "1320")


# ---------- 2b. probe orders OFF: the simulated ticket IS the position ----------
# Nothing is sent on this path, so the parent never sets FILLED on an accepted
# ack. monitor_positions() filters on FILLED/MONITORING - measured 2026-11-02
# 09:10, where 7 booked tickets produced "All paper positions resolved." at the
# open and a zero-trade report 27 seconds into the session.
o, sig, t = place("stop", 510.0, G.Direction.SHORT, send_probe=False)
check("probe orders OFF sends nothing to the broker", o is None, o)
check("probe orders OFF still opens the simulated position",
      sig.state == G.PositionState.FILLED and "2345" in t.active_positions,
      (sig.state, list(t.active_positions)))
check("probe orders OFF leaves the acceptance gate with no sample",
      not t.exec_stats.get("orders"), t.exec_stats.get("orders"))


# ---------- 3. an unarmed stop must not read as "already stopped" ----------
def monitor(sl_price, price):
    t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
    t.config = G.Config()
    t.config.paper_send_probe_orders = True
    t.config.paper_poll_sec = 0.05
    t.config.force_exit_time = "23:55"
    lg = logging.getLogger("m" + str(id(t)))
    lg.handlers = [logging.NullHandler()]
    t.log = lg
    t.running = True
    t.closed_trades = []
    t.exec_stats = {"t_open": time.time() - 5.0}
    t._smart_reports = []
    t.signals = []
    sig = G.Signal(symbol="3105", name="t", direction=G.Direction.SHORT,
                   open_price=523.0, prev_close=500.0, raw_gap=0.05, adj_gap=0.05)
    sig.entry_price, sig.shares = 523.0, 2000
    sig.sl_price, sig.tp_price = sl_price, 500.0
    sig._real_entry, sig._slip_measured = 523.0, False
    sig.state = G.PositionState.FILLED
    t.active_positions = {"3105": sig}

    def fetch(syms):
        t.running = False                 # one poll is enough
        return {"3105": price}
    t._fetch_prices = fetch
    t.monitor_positions()
    return [x["reason"] for x in t.closed_trades]


check("unarmed stop at 549 does not invent a STOP_LOSS", monitor(0.0, 549.0) == [],
      monitor(0.0, 549.0))
check("armed stop still fires", monitor(540.0, 549.0) == ["STOP_LOSS"], monitor(540.0, 549.0))
check("take profit still fires when the stop is unarmed",
      monitor(0.0, 499.0) == ["TAKE_PROFIT"], monitor(0.0, 499.0))

bad = [x for x in results if not x]
print("-" * 60)
print(f"  {len(results) - len(bad)}/{len(results)} checks passed")
sys.exit(1 if bad else 0)
