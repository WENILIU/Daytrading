"""Search the risk parameters on 2014-2021 only, then report 2022-2026 untouched.

The model, the signal pool and the exit rule are fixed everywhere; only the risk
parameters are chosen. Selecting them on the first eight years and reporting the
last five is the part that decides whether "100 pct a year" is a property of the
strategy or a property of the search.

exposure is NOT leverage here unless expo_max says so. It raises the ceiling the
capital check hands out, which stops later signals from being starved; if the
maximum daily deployment against the book stays under 100 pct nothing is borrowed.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP0 = T.CAP0
TRAIN = range(2014, 2022)
TEST = range(2022, 2027)


def ev(cfg):
    r = T.run(**cfg)
    y = r["yearly"]
    tr = [y[k] / CAP0 * 100 for k in sorted(y) if k in TRAIN]
    te = [y[k] / CAP0 * 100 for k in sorted(y) if k in TEST]
    return r, (np.mean(tr) if tr else 0.0), (np.mean(te) if te else 0.0), min(te) if te else 0.0


BRAKES = {
    "live -0.6/-1.2": ((-0.006, 0.30), (-0.012, 0.12)),
    "-1.5/-3": ((-0.015, 0.40), (-0.030, 0.15)),
    "-3/-6": ((-0.030, 0.40), (-0.060, 0.15)),
    "-5/-10": ((-0.050, 0.50), (-0.100, 0.20)),
    "off": None,
}
GRID = []
for bk, bv in BRAKES.items():
    for liq in (0.10, 0.25):
        for gap_max in (None, 0.10, 0.07):
            for exposure in (1.0, 2.0, 3.0):
                GRID.append(dict(brake=bv, liq=liq, slip_scale=1.0,
                                 gap_max=gap_max, exposure=exposure, _bk=bk))

res = []
for cfg in GRID:
    c = {k: v for k, v in cfg.items() if not k.startswith("_")}
    r, tr, te, teworst = ev(c)
    res.append((cfg, r, tr, te, teworst))
    print(".", end="", flush=True)
print()
print()
ok = [x for x in res if x[1]["mdd"] >= -5.0]
ok.sort(key=lambda x: -x[2])
print("selected on 2014-2021, validated on 2022-2026. All at slip_scale=1.00 (09:01 fill).")
print("  %-15s %-5s %-7s %-9s %8s %8s %8s %8s %7s %8s %7s" %
      ("brake", "liq", "gapmax", "exposure", "MDD%", "train%", "test%", "testworst%", "筆/日", "曝險max%", "煞車%"))
for cfg, r, tr, te, teworst in ok[:22]:
    print("  %-15s %-5s %-7s %-9s %+8.2f %+8.1f %+8.1f %+8.1f %7.1f %8.1f %7.1f" %
          (cfg["_bk"], cfg["liq"], cfg.get("gap_max", "-"), cfg["exposure"], r["mdd"],
           tr, te, teworst, r["per_day"], r["expo_max"], r["brake_pct"]))
print()
no_margin = [x for x in ok if x[1]["expo_max"] <= 100.0]
print("  MDD>=-5%%: %d   of which need no margin (max deployment <= 100%% of book): %d"
      % (len(ok), len(no_margin)))
both = [x for x in no_margin if x[3] >= 100.0]
print("  ... and still clear 100%% a year on the 2022-2026 validation window: %d" % len(both))
for cfg, r, tr, te, teworst in both[:10]:
    print("    %-15s liq=%-5s gapmax=%-6s exposure=%-4s  MDD %+5.2f%%  train %+6.1f%%  test %+6.1f%%  worst test year %+6.1f%%"
          % (cfg["_bk"], cfg["liq"], cfg.get("gap_max", "-"), cfg["exposure"],
             r["mdd"], tr, te, teworst))
