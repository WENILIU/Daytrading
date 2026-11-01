"""The 1.75x candidate showed MDD -4.15 pct at gap_max 0.07 but -5.31 pct at 0.06.
That swing is bigger than the noise floor, so one cell cannot be trusted. Sweep the
whole exposure x gap grid and report the RANGE of MDD inside each row: a row whose
MDD swings across the -5 pct line is not a real configuration, it is luck.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
LIVE = ((-0.006, 0.30), (-0.012, 0.12))
GAPS = (0.04, 0.06, 0.08, None)


def ev(**cfg):
    r = T.run(**cfg)
    y = r["yearly"]
    allr = [y[k] / CAP0 * 100 for k in sorted(y)]
    return r, np.mean(allr), min(allr)


for spread, tag in ((0.0, "A 競價價進場（無價差）"), (T.SPREAD, "吃半價差")):
    print("=== %s ===" % tag)
    print("  %8s %28s %9s %9s %8s" % ("exposure", "MDD range over gap sweep", "13yr range", "best 13yr", "worst yr"))
    for ex in (1.0, 1.25, 1.5, 1.75):
        rows = []
        for gm in GAPS:
            r, al, wo = ev(brake=LIVE, liq=0.10, gap_max=gm, exposure=ex, spread=spread)
            rows.append((gm, r["mdd"], al, wo))
        mdds = [x[1] for x in rows]
        als = [x[2] for x in rows]
        print("  %8.2f  %+6.2f%% .. %+6.2f%% (spread %.2f)  %+7.1f%% .. %+7.1f%%  %+9.1f%%  %+8.1f%%"
              % (ex, min(mdds), max(mdds), max(mdds) - min(mdds), min(als), max(als), max(als),
                 min(x[3] for x in rows)))
        for gm, md, al, wo in rows:
            flag = "PASS" if md > -5.0 else "FAIL"
            print("      gap %-5s MDD %+6.2f%% %s  13yr %+7.1f%%  worst %+7.1f%%"
                  % (gm if gm else "none", md, flag, al, wo))
    print()
