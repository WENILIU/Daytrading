# -*- coding: utf-8 -*-
r"""Is the gap floor a breadth lever that is still reachable?

scale was just measured to be pure leverage (v19_size.py): p90 exposure is already
99.4 pct at scale 1.0, so bigger orders only raise the quiet mornings and the MDD
moves with the mean, not the tail. That leaves breadth as the only way to add return
that is not leverage - more independent bets at the same per-name size.

The floor is SHORT 1.5 pct / LONG 5 pct. If the signal table already contains
sub-1.5 pct signals, lowering the floor is a filter change. If it does not, the
floor is baked into v13_build and reaching it means rebuilding the signal table -
a different size of job, and worth knowing before committing to it.
"""
import pandas as pd, numpy as np
S = pd.read_pickle("signals_v13.pkl")
S["adj_gap"] = pd.to_numeric(S["adj_gap"], errors="coerce")
S["direction"] = S["direction"].astype(str)
for dirn, floor in (("SHORT", 0.015), ("LONG", 0.05)):
    d = S[S.direction == dirn].copy()
    d["ag"] = d.adj_gap.abs()
    print("=== %s: %d signals, floor is %.1f pct ===" % (dirn, len(d), floor * 100))
    print("   min |adj_gap| in the table: %.4f" % d.ag.min())
    for lo, hi in ((0.0, 0.005), (0.005, 0.010), (0.010, 0.015), (0.015, 0.020), (0.020, 0.030)):
        n = ((d.ag >= lo) & (d.ag < hi)).sum()
        print("   %.3f <= |gap| < %.3f : %6d" % (lo, hi, n))
    print()
print("the table itself starts at the floor, so sub-floor signals were never built.")
print("Lowering the floor is a v13_build change, not a filter in v13_target.")
