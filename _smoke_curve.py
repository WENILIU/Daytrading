"""Live smoke test of the recorder against the real feed (no broker, no orders).

The offline suite proves the maths and the thread. It cannot prove that Fugle's
closePrice actually arrives in the z field, or that the session-date comparison matches
today on a real answer. Run any time; after the close the feed answers with the last
session, which still exercises the mapping.
"""
import sys, io, time, logging, tempfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
import warnings; warnings.filterwarnings("ignore")
import gap_fade_auto as G

t = G.GapFadeAutoTrader.__new__(G.GapFadeAutoTrader)
t.config = G.Config()
t.config.log_dir = tempfile.mkdtemp()
msgs = []
lg = logging.getLogger("smoke")
lg.handlers = [type("H", (logging.Handler,), {"emit": lambda self, r: msgs.append(r.getMessage())})()]
lg.setLevel(logging.INFO)
t.log = lg
t.exec_stats = {"orders": [], "entry_slippage": []}

rows, src = t._batch_scan(["2330", "2454", "2492"])
print(f"source: {src} | rows: {len(rows)}")
for r in rows[:3]:
    print(f"  {r.get('c')} open={r.get('o')} last(z)={r.get('z')} prev={r.get('y')} "
          f"session={G._session_date(r.get('d'))!r}")
ok_z = all(float(r.get("z") or 0) > 0 for r in rows if r.get("c"))
print(f"\n  every row carries a current price: {ok_z}")

import datetime as dt
today = dt.date.today().isoformat()
dated = sum(1 for r in rows if G._session_date(r.get("d")) == today)
print(f"  rows on today's session ({today}): {dated}/{len(rows)}"
      + ("  <- market closed, feed answers with the last session; expected 0"
         if dated == 0 else ""))

t.exec_stats["t_open"] = time.time() - 0.3
sigs = [G.Signal(symbol="2492", name="X", direction=G.Direction.SHORT, open_price=100.0,
                 prev_close=95.0, raw_gap=0.05, adj_gap=0.05),
        G.Signal(symbol="2454", name="Y", direction=G.Direction.LONG, open_price=4000.0,
                 prev_close=4200.0, raw_gap=-0.05, adj_gap=-0.05)]
th = t._start_entry_curve_recorder(sigs, seconds=4.0, poll=1.0)
th.join(15.0)
curve = t.exec_stats.get("entry_curve") or {}
print(f"\n  recorder collected {len(curve)} codes, "
      f"{sum(len(v['points']) for v in curve.values())} points")
for r in G._wait_curve_summary(curve):
    if r["n"]:
        print(f"    +{r['offset_sec']:<3} reach={r['n']} adverse_p50={r['adverse_p50']} "
              f"short={r['short_p50']} long={r['long_p50']}")
for m in msgs:
    if "entry-curve" in m:
        print("  log:", m)
print("\n  SMOKE OK" if ok_z and curve else "\n  SMOKE INCONCLUSIVE")
