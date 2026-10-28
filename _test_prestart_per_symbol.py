"""Reproduce the 2026-10-28 failure: a late-start session where the first poll
returns no price for a name, so its first REAL observation happens on a later
iteration. The exit must still be tagged _PRESTART.

Before the fix, late_start was tied to first_poll, so this produced a plain
STOP_LOSS and two invented losses (-50,533) entered the book untagged.
"""
import sys, time, warnings, logging
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G


def run_case(first_poll_has_price, started_after_open):
    t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
    t.config = G.Config()
    t.config.paper_poll_sec = 0.05
    t.config.force_exit_time = "23:55"      # keep the window open for the test
    lg = logging.getLogger("m" + str(id(t)))
    lg.handlers = [logging.NullHandler()]
    t.log = lg
    t.running = True
    t.closed_trades = []
    t.exec_stats = {"t_open": time.time() - (2228.0 if started_after_open else 5.0)}
    t._smart_reports = []
    t.signals = []

    sig = G.Signal(symbol="3105", name="test", direction=G.Direction.SHORT,
                   open_price=523.0, prev_close=500.0, raw_gap=0.05, adj_gap=0.05)
    sig.entry_price, sig.shares = 523.0, 2000
    sig.sl_price, sig.tp_price = 540.0, 500.0
    # _place_entry_order sets both of these in production (gap_fade_auto.py:3114,
    # 3116); this test drives monitor_positions directly, so set them the same way.
    sig._real_entry = 523.0
    sig._slip_measured = False
    sig.state = G.PositionState.FILLED
    t.active_positions = {"3105": sig}

    calls = {"n": 0}

    def fetch(syms):
        calls["n"] += 1
        if calls["n"] == 1 and not first_poll_has_price:
            return {}                      # the 2026-10-28 shape
        return {"3105": 540.0}             # already through the stop
    t._fetch_prices = fetch

    t.monitor_positions()
    return ([x["reason"] for x in t.closed_trades],
            t.exec_stats.get("entry_slippage", []))


results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(f"  [{'OK  ' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {detail}"))


print("1) late start, first poll has NO price (the 2026-10-28 shape)")
r, sl = run_case(False, True)
check("exit is tagged STOP_LOSS_PRESTART, not a plain STOP_LOSS",
      r == ["STOP_LOSS_PRESTART"], r)
check("slippage IS still measured for a name whose first price arrives on poll 2",
      len(sl) == 1 and sl[0]["symbol"] == "3105", sl)

print("2) late start, first poll DOES have the price")
r2, sl2 = run_case(True, True)
check("also tagged STOP_LOSS_PRESTART", r2 == ["STOP_LOSS_PRESTART"], r2)
check("slippage measured exactly once", len(sl2) == 1, sl2)

print("3) started before the open (normal run), first poll has the price")
r3, sl3 = run_case(True, False)
check("genuine STOP_LOSS - no PRESTART tag", r3 == ["STOP_LOSS"], r3)
check("slippage measured exactly once", len(sl3) == 1, sl3)

print()
ok = all(results)
print(f"{sum(results)}/{len(results)} -> " + ("ALL OK" if ok else "FAILED"))
sys.exit(0 if ok else 1)
