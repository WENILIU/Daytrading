"""One iteration of the paper monitor, with the clock forced to a late start,
to prove the PRESTART tag fires and settles at the level rather than the price."""
import sys, time, warnings, logging, tempfile
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

cfg = G.Config(); cfg.log_dir = tempfile.mkdtemp(prefix="pre_")
t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
t.config = cfg
lg = logging.getLogger("t"); lg.addHandler(logging.StreamHandler(sys.stdout)); lg.setLevel(logging.INFO)
t.log = lg
t.running = True
t.closed_trades = []
t.exec_stats = {"t_open": time.time() - 600.0}   # observation begins 10 min late
t.active_positions = {}
sig = G.Signal(symbol="9999", name="TEST", direction=G.Direction.SHORT, open_price=105.0,
               prev_close=100.0, raw_gap=0.05, adj_gap=0.05)
sig.state = G.PositionState.FILLED
sig.entry_price, sig.shares = 105.0, 1000
sig.sl_price, sig.tp_price = 111.3, 100.8
t.active_positions["9999"] = sig

calls = {"n": 0}
def fake_fetch(syms):
    calls["n"] += 1
    t.running = False          # stop after one round
    return {"9999": 115.0}    # already well past the 111.3 stop
t._fetch_prices = fake_fetch
t._parse_time = lambda s: __import__("datetime").datetime.now().replace(hour=23, minute=0, second=0, microsecond=0)

t.monitor_positions()
tr = t.closed_trades[0]
print("\nreason      :", tr["reason"])
print("exit price  :", tr["exit"], "(sl_price =", sig.sl_price, ")")
print("rounds run  :", calls["n"])
assert tr["reason"] == "STOP_LOSS_PRESTART", tr["reason"]
assert tr["exit"] == sig.sl_price, tr["exit"]
print("\nOK: late start settles at the level and is tagged PRESTART")
