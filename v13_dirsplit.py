"""gap_max was one number for both directions, but LONG signals only exist above 5 pct
gap while SHORT start at 1.5 pct. So the 'robust' gap_max 0.04 is really a SHORT-only
book. Cap the two directions separately and see what each side is actually worth.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
TEST = range(2022, 2027)
LIVE = ((-0.006, 0.30), (-0.012, 0.12))


def ev(**cfg):
    r = T.run(**cfg)
    y = r["yearly"]
    allr = [y[k] / CAP0 * 100 for k in sorted(y)]
    te = [y[k] / CAP0 * 100 for k in sorted(y) if k in TEST]
    return r, np.mean(allr), np.mean(te), min(allr)


def split(r):
    n = r["dir_n"]; y = r["dir_y"]
    tot = sum(y.values()) or 1.0
    return ("S %5d 筆 %+7.0f 萬 (%4.1f%%)  L %5d 筆 %+7.0f 萬 (%4.1f%%)"
            % (n["SHORT"], y["SHORT"] / 1e4, y["SHORT"] / tot * 100,
               n["LONG"], y["LONG"] / 1e4, y["LONG"] / tot * 100))


print("=== what the shipped v14 (gap_max 0.06, exposure 1.25) is made of ===")
r, al, te, wo = ev(brake=LIVE, liq=0.10, gap_max=0.06, exposure=1.25, spread=0.0)
print("  MDD %+.2f%%  13yr %+.1f%%  筆/日 %.1f" % (r["mdd"], al, r["per_day"]))
print("  " + split(r))
print()
print("=== direction-aware caps, exposure 1.75 ===")
print("  %6s %6s %8s %9s %9s %8s %6s   %s" % ("SHORT", "LONG", "MDD%", "13yr", "test", "worst", "筆/日", "多空貢獻"))
for sc in (0.04, 0.05, 0.06, 0.08, None):
    for lc in (None, 0.08, 0.10):
        if lc is not None and sc is not None and lc == sc:
            continue
        r, al, te, wo = ev(brake=LIVE, liq=0.10, gap_max=sc, gap_max_long=lc, exposure=1.75, spread=0.0)
        print("  %6s %6s %+8.2f %+9.1f %+9.1f %+8.1f %6.1f   %s"
              % (sc if sc else "none", lc if lc else "none", r["mdd"], al, te, wo, r["per_day"], split(r)))
