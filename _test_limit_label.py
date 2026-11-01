# -*- coding: utf-8 -*-
r"""The stop that binds is the stop that gets named.

exit_of_legal used to decide "was this a price-limit stop" by testing
slp < entry*(1+SLO). But slp is snap_price(...), rounded to the nearest price the
exchange accepts, so an ordinary 4% stop lands below its own trigger about half
the time and was named 停損(觸漲停上限). Measured 2026-11-02 on the shipped book:
that bucket held 3,385 trades when only 105 were limit-bound - 32x - and every
downstream number built on it (the +21 pct "cost of the limit-lock rule", the
22.0% exit-mix line, the +95.9% upper bound) was describing the ordinary
stop-loss instead.

The test cases below are the two shapes that broke it: a 4% stop that snaps DOWN
(SHORT) or UP (LONG) while the price limit is nowhere near.
"""
import sys
sys.path.insert(0, ".")
from v13_engine import exit_of_legal, snap_price, SLO

fails = []


def check(name, got, want):
    if got != want:
        fails.append("%s: got %r want %r" % (name, got, want))


# --- A: the price limit really is the tighter stop (SHORT) ---
# entry 100, limit-up 101 -> limit stop 100.9 is nearer than the 4% stop 104.0
ex, slp, tpp, why, gross = exit_of_legal("SHORT", 100.0, 101.0, 99.0, 100.2,
                                         101.0, 99.0, 0.1, 0.12)
check("A exit", ex, 100.9)
check("A reason", why, "停損(觸漲停上限)")

# --- B: the ordinary 4% stop, snapped DOWN, with the limit far away (SHORT) ---
# entry 40.98 -> 4% stop 42.6192 -> snaps to 42.60, which is BELOW its own
# trigger. The limit is 59.90. Old code called this a limit touch.
entry, lu = 40.98, 60.0
normal = snap_price(entry * (1 + SLO))
assert normal < entry * (1 + SLO), "case B needs a snap that rounds down, got %s" % normal
ex, slp, tpp, why, gross = exit_of_legal("SHORT", entry, 43.0, 41.0, 41.5,
                                         lu, 36.0, 0.1, 0.12)
check("B exit", ex, normal)
check("B reason", why, "停損 SL")

# --- C: same shape on the LONG side, snapped UP toward limit-down ---
entry, ld = 40.98, 20.0
normal = snap_price(entry * (1 - SLO))
assert normal > entry * (1 - SLO), "case C needs a snap that rounds up, got %s" % normal
ex, slp, tpp, why, gross = exit_of_legal("LONG", entry, 41.5, 39.0, 40.0,
                                         45.0, ld, 0.05, 0.12)
check("C exit", ex, normal)
check("C reason", why, "停損 SL")

# --- D: the label fix must not move money. The exit price is min/max of the two
# stops either way, so gross is fixed by the arithmetic, not by the name. ---
for direction, entry, hi, lo, cl, lu, ld, tk in (
        ("SHORT", 100.0, 101.0, 99.0, 100.2, 101.0, 99.0, 0.1),
        ("SHORT", 40.98, 43.0, 41.0, 41.5, 60.0, 36.0, 0.1),
        ("LONG", 40.98, 41.5, 39.0, 40.0, 45.0, 20.0, 0.05)):
    ex, slp, tpp, why, gross = exit_of_legal(direction, entry, hi, lo, cl, lu, ld, tk, 0.12)
    if direction == "SHORT":
        want = min(snap_price(entry * (1 + SLO)), round(lu - tk, 2))
    else:
        want = max(snap_price(entry * (1 - SLO)), round(ld + tk, 2))
    check("D exit %s %s" % (direction, entry), ex, want)

# --- E: a stop that is not reached must not be named as one at all ---
ex, slp, tpp, why, gross = exit_of_legal("SHORT", 100.0, 100.5, 99.0, 100.2,
                                         101.0, 99.0, 0.1, 0.12)
check("E reason", why, "13:25 強制平倉")
check("E exit", ex, 100.2)

if fails:
    print("FAILED %d" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("OK: the limit-bound label is only used when the price limit is the binding stop,")
print("    and the exit price is unchanged by the naming.")
