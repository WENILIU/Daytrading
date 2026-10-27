"""Total-wealth comparison: cap the trading book and park the excess as 0% cash, vs no cap.

Same strategy, same 5% participation rule. The only difference is whether capital above
a threshold is withdrawn (and earns nothing) or keeps trading.
"""
import pandas as pd, numpy as np, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import backtest_dyn_pure as B

USE_K, USE_DS, MIN_POS = False, False, 0.005
YEARS = range(2014, 2027)

print(f"{'cap(wan)':>10}{'tradeEnd(wan)':>15}{'withdrawn(wan)':>16}{'TOTAL(yi)':>11}{'TOTAL CAGR%':>13}{'tradeCAGR%':>12}{'worstYr%':>10}")
print("-" * 88)
for cap in [20_000_000, 50_000_000, 100_000_000, 200_000_000, None]:
    eq = 4_500_000; wd = 0.0; worst = 1e9; trade_peak = 4_500_000; trade_cagr_pts = []
    for y in YEARS:
        r = B.run_year(eq, y, None, USE_K, USE_DS, MIN_POS)
        if r is None:
            continue
        final, ret, dd, shp, nt, nd, mtv, _ = r
        worst = min(worst, ret)
        if cap is not None and final > cap:
            wd += final - cap; final = cap
        eq = final
    total = eq + wd
    ny = 13
    tc = (total / 4_500_000) ** (1 / ny) - 1
    tradec = (eq / 4_500_000) ** (1 / ny) - 1
    lbl = "NO CAP" if cap is None else f"{cap/1e4:.0f}"
    print(f"{lbl:>10}{eq/1e4:>15.0f}{wd/1e4:>16.0f}{total/1e8:>11.2f}{tc*100:>13.1f}{tradec*100:>12.1f}{worst:>+10.1f}")
