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
    ("_test_canary.py",
     "the canary picks the cheapest LONG and sends 1 張 現股買 at 跌停"),
    ("_test_pre.py",
     "a late start must not invent a fill out of a level it never saw crossed"),
    ("_test_t1_panel_age.py",
     "the factor panel is judged against the previous SESSION, not calendar days "
     "(a Monday would have failed a correct Friday panel)"),
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
            r = subprocess.run([sys.executable, str(path)], cwd=str(HERE),
                               capture_output=True, text=True, timeout=180)
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
