# -*- coding: utf-8 -*-
"""The entry-timing curve must answer the wait-vs-go question, not flatter it.

Measured 2026-10-28: scanning once at 09:00 sees 36 pct of the day's signals by +05s
and 57 pct by +10s, and the cost of waiting was only ever estimated from 1-minute bars,
which cannot resolve 30 seconds. These assertions are what stop the new recorder from
reporting a number that looks better than reality:

  * a name that first prints at +8s is NOT tradeable at +2s,
  * SHORT and LONG move opposite ways on the same price path, so one blended number
    would cancel a real cost against a real gain,
  * the feed's session date has two formats, and comparing them raw made a live TWSE
    fallback report itself as dead.
"""
import sys, time, logging, tempfile, warnings
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import gap_fade_auto as G

results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(f"  [{'OK  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if not cond else ""))


# --- the two date formats are both real, read from the live APIs 2026-10-28 ----
check("Fugle ISO date normalises to itself",
      G._session_date("2026-10-28") == "2026-10-28", repr(G._session_date("2026-10-28")))
check("TWSE compact date normalises to the same string (this used to never match)",
      G._session_date("20261028") == "2026-10-28", repr(G._session_date("20261028")))
check("an unparseable date says unknown instead of guessing",
      G._session_date(None) == "" and G._session_date("abc") == "" and G._session_date(0) == "")

# --- sign convention: POSITIVE = WORSE, and it flips with direction ------------
check("SHORT: price below the open is a LOSS of opportunity (positive)",
      abs(G._adverse_pct("SHORT", 100.0, 99.0) - 1.0) < 1e-9,
      str(G._adverse_pct("SHORT", 100.0, 99.0)))
check("LONG: the same price path is a GAIN (negative)",
      abs(G._adverse_pct("LONG", 100.0, 99.0) + 1.0) < 1e-9,
      str(G._adverse_pct("LONG", 100.0, 99.0)))
check("the Direction enum is accepted, not just the string",
      abs(G._adverse_pct(G.Direction.SHORT, 100.0, 99.0) - 1.0) < 1e-9)
check("a missing or impossible price is None, not 0.0 (0.0 would read as free)",
      G._adverse_pct("SHORT", 100.0, None) is None
      and G._adverse_pct("SHORT", 100.0, 0) is None
      and G._adverse_pct("SHORT", 0, 99.0) is None)
check("an unknown direction is None rather than defaulting to one side",
      G._adverse_pct("", 100.0, 99.0) is None and G._adverse_pct(None, 100.0, 99.0) is None)

# --- recording ----------------------------------------------------------------
watch = {"2492": "SHORT", "3037": "LONG"}
curve = {}
t0 = 1_000.0
added = G._wait_curve_record(curve, [
    {"c": "2492", "o": 100.0, "z": 99.0},          # SHORT, price fell -> favourable
    {"c": "3037", "o": 50.0, "z": 51.0},           # LONG, price rose -> adverse
    {"c": "9999", "o": 10.0, "z": 11.0},           # not wanted
    {"c": "2492", "o": 100.0},                     # no current price
    {"c": "3037", "o": 0, "z": 51.0},              # no open price
], watch, t0, t0 + 8.0)
check("only the names we actually want to trade are recorded",
      added == 2 and set(curve) == {"2492", "3037"}, f"added={added} keys={sorted(curve)}")
check("a row without a readable price is skipped, not recorded as 0",
      len(curve["2492"]["points"]) == 1 and len(curve["3037"]["points"]) == 1)
G._wait_curve_record(curve, [{"c": "2492", "o": 100.0, "z": 98.0}], watch, t0, t0 + 8.2)
check("two reads inside the same poll interval do not double-count one moment",
      len(curve["2492"]["points"]) == 1, str(curve["2492"]["points"]))
G._wait_curve_record(curve, [{"c": "2492", "o": 100.0, "z": 97.0}], watch, t0, t0 + 30.0)
check("a later poll does add a new point", len(curve["2492"]["points"]) == 2)

# --- the rule that makes the curve honest --------------------------------------
at2 = G._wait_curve_at(curve, 2.0)
check("a name that first prints at +8s is NOT counted as tradeable at +2s",
      len(at2["short"]) == 1 and len(at2["long"]) == 1, str(at2))
check("and acting at +2s is priced at the +8s print, because that is the first "
      "price you could actually have got",
      abs(at2["short"][0] - 1.0) < 1e-9, str(at2["short"]))
at20 = G._wait_curve_at(curve, 20.0)
check("waiting past a poll uses the LATER price, not the stale early one",
      abs(at20["short"][0] - 3.0) < 1e-9, str(at20["short"]))
at999 = G._wait_curve_at(curve, 999.0)
check("past the last read nothing is reachable - it is counted unseen, not zero cost",
      at999["short"] == [] and at999["long"] == [] and at999["unseen"] == 2, str(at999))

# --- summary ------------------------------------------------------------------
rows = G._wait_curve_summary(curve, offsets=(2, 30, 999))
check("summary keeps SHORT and LONG apart instead of averaging a cost against a gain",
      all("short_p50" in r and "long_p50" in r for r in rows))
check("a SHORT priced below the open is adverse (positive) - we sell into it",
      rows[0]["short_p50"] is not None and rows[0]["short_p50"] > 0, str(rows[0]))
flip = {}
G._wait_curve_record(flip, [{"c": "2492", "o": 100.0, "z": 99.0},
                            {"c": "3037", "o": 100.0, "z": 99.0}],
                     {"2492": "SHORT", "3037": "LONG"}, t0, t0 + 5.0)
f1 = G._wait_curve_summary(flip, offsets=(2,))[0]
check("the SAME price path is adverse for SHORT and favourable for LONG - one blended "
      "column would cancel a real cost against a real gain and hide the whole point",
      f1["short_p50"] > 0 and f1["long_p50"] < 0, str(f1))
check("the adverse LONG move is reported as adverse (positive)",
      rows[0]["long_p50"] is not None and rows[0]["long_p50"] > 0, str(rows[0]))
check("an offset with nothing reachable reports n=0, it does not invent a percentile",
      rows[2]["n"] == 0 and rows[2]["adverse_p50"] is None, str(rows[2]))
check("the default offsets still cover the 30s point that 1-minute bars cannot",
      30 in G.WAIT_OFFSETS and 15 in G.WAIT_OFFSETS, str(G.WAIT_OFFSETS))

# --- percentile convention must match the RISK1 summary it will be read beside --
vals = list(range(1, 101))
lats = sorted(vals)
n = len(lats)
check("_q uses the same nearest-rank rule as the RISK1 line, so the two are comparable",
      G._q(vals, 0.9) == lats[min(n - 1, int(0.9 * n))], f"{G._q(vals, 0.9)}")

# --- recorder wiring ---------------------------------------------------------
t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
t.config = G.Config()
t.config.log_dir = tempfile.mkdtemp()
msgs = []
lg = logging.getLogger("ec" + str(id(t)))
lg.handlers = [type("H", (logging.Handler,),
                   {"emit": lambda self, r: msgs.append(r.getMessage())})()]
lg.setLevel(logging.INFO)
t.log = lg
t.exec_stats = {"orders": [], "entry_slippage": [], "t_open": time.time() - 0.2}
calls = []


def fake_batch(codes):
    calls.append(list(codes))
    return [{"c": c, "o": 100.0, "z": 99.0} for c in codes], "fake"


t._batch_scan = fake_batch
sigs = [G.Signal(symbol="2492", name="X", direction=G.Direction.SHORT, open_price=100.0,
                 prev_close=95.0, raw_gap=0.05, adj_gap=0.05),
        G.Signal(symbol="3037", name="Y", direction=G.Direction.LONG, open_price=50.0,
                 prev_close=52.0, raw_gap=-0.04, adj_gap=-0.04)]
th = t._start_entry_curve_recorder(sigs, seconds=1.2, poll=0.2)
check("the recorder starts", th is not None)
if th:
    th.join(8.0)
curve2 = t.exec_stats.get("entry_curve") or {}
check("the watch list is built from real Signal objects, Direction enum included",
      set(curve2) == {"2492", "3037"}, f"keys={sorted(curve2)}")
check("it polls only the names we want, never the whole market",
      bool(calls) and all(set(c) <= {"2492", "3037"} for c in calls), str(calls[:1]))
check("points reach exec_stats, which is the copy the end-of-day report reads",
      bool(curve2) and all(v["points"] for v in curve2.values()), str(curve2))
check("directions survive the enum->string hop so SHORT/LONG stay separated",
      all(v["direction"] in ("SHORT", "LONG") for v in curve2.values()),
      str({k: v.get("direction") for k, v in curve2.items()}))
check("it stops by itself instead of polling for the rest of the session",
      not th.is_alive() if th else True)
check("and it reports how much it collected, so an empty curve is not silent",
      any("entry-curve recorder" in m for m in msgs), str(msgs[-2:]))

t2 = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
t2.config = G.Config(); t2.config.log_dir = tempfile.mkdtemp()
t2.log = logging.getLogger("ec0" + str(id(t2))); t2.log.addHandler(logging.NullHandler())
t2.exec_stats = {"orders": [], "entry_slippage": []}
check("no signals means no thread, not a thread that polls an empty list",
      t2._start_entry_curve_recorder([]) is None)

print()
ok = all(results)
print(f"{sum(results)}/{len(results)} checks passed -> " + ("ALL OK" if ok else "FAILED"))
sys.exit(0 if ok else 1)
