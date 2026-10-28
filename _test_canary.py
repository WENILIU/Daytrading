"""Offline test of the canary: it must pick the cheapest LONG, send 現股買 at
跌停, and query the smart report. No COM, no market."""
import sys, warnings, logging, tempfile
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

cfg = G.Config()
t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
t.config = cfg
lg = logging.getLogger("t"); lg.addHandler(logging.StreamHandler(sys.stdout))
lg.setLevel(logging.INFO); t.log = lg
t.exec_stats = {"orders": []}
t._smart_reports = []
t.active_positions = {}

def mk(sym, d, px):
    s = G.Signal(symbol=sym, name=sym, direction=d, open_price=px, prev_close=px,
                 raw_gap=0.0, adj_gap=0.0)
    s.entry_price, s.shares = px, 1000
    s.sl_price, s.tp_price = px * 1.05, px * 0.9
    return s

t.signals = [mk("1111", G.Direction.SHORT, 90.0),      # cheapest but SHORT
             mk("2222", G.Direction.LONG, 500.0),       # LONG, expensive
             mk("3333", G.Direction.LONG, 45.0)]        # cheapest LONG

sent = []
def fake_place(sig):
    lu, ld = G.calc_price_limits(sig.prev_close)
    assert sig.entry_price == ld, f"expected 跌停 {ld}, got {sig.entry_price}"
    assert sig.direction == G.Direction.LONG
    sent.append({"symbol": sig.symbol, "price": sig.entry_price,
                 "buy_sell": 0 if sig.direction == G.Direction.LONG else 1})
    t.exec_stats["orders"].append({"symbol": sig.symbol, "ack_code": 0,
                                   "direction": sig.direction.value})
t._place_entry_order = fake_place
t.request_smart_report = lambda *a, **k: t._smart_reports.append(
    {"ts": "now", "row": "TS,913R0438724,3333,DayTrade,待成交,45"})

t._send_canary()
print("\nsent:", sent)
print("smart rows seen:", len(t._smart_reports))
assert sent == [{"symbol": "3333", "price": 40.5, "buy_sell": 0}], sent
assert len(t._smart_reports) >= 1
print("\nOK: canary picks the cheapest LONG, buys at 跌停, and queries the report")

print("\n--- fallback: no LONG candidates at all ---")
t2 = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
t2.config = cfg; t2.log = lg; t2.exec_stats = {"orders": []}
t2._smart_reports = []; t2.active_positions = {}
t2.signals = [mk("4444", G.Direction.SHORT, 60.0)]
sent2 = []
def fake2(sig):
    assert sig.direction == G.Direction.LONG, "fallback must convert to 現股買"
    assert sig.state == G.PositionState.PENDING
    sent2.append(sig.symbol)
    t2.exec_stats["orders"].append({"symbol": sig.symbol, "ack_code": 0})
t2._place_entry_order = fake2
t2.request_smart_report = lambda *a, **k: t2._smart_reports.append({"ts": "n", "row": "x"})
t2._send_canary()
print("sent:", sent2)
assert sent2 == ["4444"]
print("original signal untouched:", t.signals[0].direction)
assert t.signals[0].direction == G.Direction.SHORT
print("OK: fallback converts a copy, the real signal keeps its direction")
