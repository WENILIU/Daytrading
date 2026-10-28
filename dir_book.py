"""What is the 無券當沖 qualification worth? Re-run the live-exact book with the
signal pool restricted to one direction, using the canonical sizing path."""
import pandas as pd, numpy as np, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import backtest_dyn_pure as B

FULL_G = dict(B.G_all)
USE_K, USE_DS, MIN_POS = False, False, 0.005   # live-exact


def restrict(keep):
    g = {}
    for dt, sub in FULL_G.items():
        s = sub[sub["direction"] == keep]
        if len(s):
            g[dt] = s
    B.G_all = g
    return len(g)


def book(keep):
    nd = restrict(keep)
    rows = []
    for y in range(2014, 2027):
        r = B.run_year(4_500_000, y, None, USE_K, USE_DS, MIN_POS)
        if r is None:
            continue
        final, ret, dd, shp, nt, ndays, mtv, _ = r
        rows.append((y, ret, dd, shp, nt / ndays, nt))
    return rows, nd


for keep, label in [("SHORT", "SHORT only (needs 無券當沖)"),
                    ("LONG", "LONG only (現股當沖, works today)"),
                    ("BOTH", "BOTH (current strategy)")]:
    if keep == "BOTH":
        B.G_all = dict(FULL_G)
        nd = len(FULL_G)
        rows = []
        for y in range(2014, 2027):
            r = B.run_year(4_500_000, y, None, USE_K, USE_DS, MIN_POS)
            if r is None:
                continue
            final, ret, dd, shp, nt, ndays, mtv, _ = r
            rows.append((y, ret, dd, shp, nt / ndays, nt))
    else:
        rows, nd = book(keep)
    rets = [r[1] for r in rows]
    print()
    print("=" * 74)
    print(f"{label}   signal-pool days: {nd}")
    print("=" * 74)
    print(f"{'Year':<6}{'Ret%':>9}{'MDD%':>8}{'Sharpe':>8}{'Tr/day':>8}{'fills':>8}")
    for y, ret, dd, shp, tpd, nt in rows:
        print(f"{y:<6}{ret:>+9.1f}{dd:>8.1f}{shp:>8.2f}{tpd:>8.1f}{nt:>8}")
    print("-" * 50)
    print(f"{'AVG':<6}{np.mean(rets):>+9.1f}{min(r[2] for r in rows):>8.1f}"
          f"{np.mean([r[3] for r in rows]):>8.2f}{np.mean([r[4] for r in rows]):>8.1f}")
    print(f"  all years positive: {all(r > 0 for r in rets)} | worst {min(rets):+.1f}% "
          f"| best {max(rets):+.1f}% | total PnL {sum((x/100)*4_500_000 for x in rets)/1e4:,.0f} wan")
