"""Can relaxing the participation rule restore CAGR once capital is uncapped?

min_turnover = PART * equity  ->  one-way participation = 25% / PART.
PART=5 -> 5% participation (current live rule). Smaller PART = more aggressive.
Pure compounding, no capital cap, live-exact config.
"""
import pandas as pd, numpy as np, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import backtest_dyn_pure as B

USE_K, USE_DS, MIN_POS = False, False, 0.005

print(f"{'PART':>5}{'partic%':>9}{'final(yi)':>11}{'CAGR%':>8}{'MDD%':>8}{'Sharpe':>8}{'Tr/day 2014':>13}{'Tr/day 2026':>13}{'univ 2026':>11}")
print("-" * 88)
for PART in [5.0, 4.0, 3.0, 2.0, 1.5, 1.0, 0.5]:
    B.PART = PART
    eq = 4_500_000
    ser = []
    fills = {}
    for y in range(2014, 2027):
        r = B.run_year(eq, y, None, USE_K, USE_DS, MIN_POS)
        if r is None:
            continue
        final, ret, dd, shp, nt, nd, mtv, curve = r
        fills[y] = (nt / nd, mtv)
        vals = pd.Series(np.asarray(curve.values, dtype=float),
                         index=pd.DatetimeIndex(sorted([d for d in B.G_all if pd.Timestamp(d).year == y])))
        ser.append(vals)
        eq = final
    c = pd.concat(ser)
    ny = len(set(c.index.year))
    cagr = (c.iloc[-1] / 4_500_000) ** (1 / ny) - 1
    dd = ((c - c.cummax()) / c.cummax()).min() * 100
    rr = c.pct_change().fillna(0)
    sh = rr.mean() / rr.std() * np.sqrt(243)
    print(f"{PART:>5.1f}{100*0.25/PART:>9.1f}{c.iloc[-1]/1e8:>11.2f}{cagr*100:>8.1f}{dd:>8.2f}{sh:>8.2f}"
          f"{fills[2014][0]:>13.1f}{fills[2026][0]:>13.1f}{fills[2026][1]/1e8:>11.1f}yi")
