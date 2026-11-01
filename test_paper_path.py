"""Run the paper-mode offline test suite. No market session, no orders.

One suite (`_test_t1_panel_age.py`) reads the finlab session calendar, so it
needs the network; the rest run entirely offline.

These are the assertions behind the LIVE FEASIBILITY REPORT. They exist because
the report kept finding ways to print a PASS it had not earned (an after-hours
order answered with code 0, a canary carrying the acceptance gate, a p90
computed from six rejected orders). Run this before starting `paper` - the 08:55
flow does - and after any change to gap_fade_auto.py.

Exit code 0 means every assertion below held. It says nothing about whether the
broker will accept an order tomorrow; those three gates can only be measured
in a real session.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

SUITES = [
    ("_test_gates.py",
     "the feasibility report never reports a PASS it has not earned "
     "(after-hours / canary / n<20 / accept-vs-reject)"),
    ("_test_session_gate.py",
     "orders sent outside 09:00-13:30 are NOT TESTED, not a pass"),
    ("_test_start_guard.py",
     "paper refuses to start outside 08:55-13:25"),
    ("_test_prestart_per_symbol.py",
     "a late-start exit is tagged _PRESTART per position, and a normal start "
     "still produces a genuine STOP_LOSS"),
    ("_test_credit_line.py",
     "the notional ceiling is min(equity x multiple, the broker's ABSOLUTE line); "
     "this account has no financing, so 450 萬 is own cash and 1.90x is not "
     "available at all - 855 萬 was a notional, never a line"),
    ("_test_entry_quote.py",
     "the entry is priced from the book at +Ns (buy at the ask, sell at the bid), a "
     "missing quote skips the order instead of falling back to the open, and the cost "
     "against the open is recorded - the C arm must not come back by accident"),
    ("_test_canary.py",
     "the canary picks the cheapest LONG and sends 1 張 現股買 at 跌停"),
    ("_test_pre.py",
     "a late start must not invent a fill out of a level it never saw crossed"),
    ("_test_t1_panel_age.py",
     "the factor panel is judged against the previous SESSION, not calendar days "
     "(a Monday would have failed a correct Friday panel)"),
    ("_test_inventory_parse.py",
     "the day-trade quota reading uses the manual's 19-field layout, not the SDK "
     "struct's 18 (off by one from index 15), and no rows is not read as no quota"),
    ("_test_smart_report.py",
     "a smart-order row is only reported when every field validates against what we "
     "sent (the real 2026-10-28 rows), a fill is caught from either signal, and the "
     "## terminator is ignored instead of raising a false alarm"),
    ("_test_probe_sample.py",
     "the 09:00 quote-readiness probe samples the whole market, not the first 100 "
     "lines of a sorted file (ETFs + oldest sector), which is not the population "
     "the orders come from"),
    ("_test_scan_delay.py",
     "entry timing is a parameter that each run records, and a delay that has "
     "already passed is reported as NOT applied instead of letting a late-start "
     "slippage number be read as the strategy's"),
    ("_test_entry_curve.py",
     "the entry-timing curve prices acting at +Ns at the first print AT OR AFTER N "
     "(a name visible at +8s is not tradeable at +2s), keeps SHORT and LONG apart "
     "because the same path is a cost for one and a gain for the other, and reads "
     "both feeds' session-date formats"),
    ("_test_daytrade.py",
     "the broker's per-stock day-trade permission is reported per signal and per "
     "direction, never silently enforced, and an unread flag is NOT read as allowed"),
]


def main():
    print("=" * 78)
    print("PAPER-PATH OFFLINE TESTS")
    print("=" * 78)
    failed = []
    for name, what in SUITES:
        path = HERE / name
        if not path.exists():
            print(f"  [MISSING] {name} - {what}")
            failed.append(name)
            continue
        t0 = time.perf_counter()
        try:
            # Decode as UTF-8 on purpose. The children print Chinese, and text=True
            # without an explicit encoding uses the local codepage (cp950 here), so a
            # failing suite raised UnicodeDecodeError inside the reader thread and its
            # actual assertion message was lost - the failure was still reported, but
            # with no reason attached (measured 2026-11-01).
            r = subprocess.run([sys.executable, str(path)], cwd=str(HERE),
                               capture_output=True, text=True, timeout=180,
                               encoding="utf-8", errors="replace",
                               env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            code, out = r.returncode, (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired:
            code, out = 124, "timed out after 180s"
        dt = time.perf_counter() - t0
        if code == 0:
            print(f"  [PASS] {name:<32} {dt:5.1f}s  {what}")
        else:
            print(f"  [FAIL] {name:<32} {dt:5.1f}s  exit={code}  {what}")
            tail = [ln for ln in out.splitlines() if ln.strip()][-12:]
            for ln in tail:
                print(f"         | {ln[:160]}")
            failed.append(name)

    print("-" * 78)
    print(f"  {len(SUITES) - len(failed)}/{len(SUITES)} suites passed")
    if failed:
        print(f"  FAILED: {', '.join(failed)}")
        print("  Do not start paper from a failing suite - fix the code first.")
    else:
        print("  Paper-path code is intact. The three feasibility gates still")
        print("  need a real session; this suite only proves the report cannot")
        print("  report a PASS it has not earned.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
