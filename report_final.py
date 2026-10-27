"""Final report for Gap Fade v13: yearly + monthly, two capital modes.

D) each year restarts at 4.5M  (live-exact config; the number that maps to real trading)
F) pure compounding, NO capital cap, dynamic participation only (min_turnover = 5 x equity)

Reuses the canonical sizing/selection path in backtest_dyn_pure so numbers cannot drift.
"""
import pandas as pd, numpy as np, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import backtest_dyn_pure as B

USE_K, USE_DS, MIN_POS = False, False, 0.005   # live-exact


def series_for(eq_start, year):
    r = B.run_year(eq_start, year, None, USE_K, USE_DS, MIN_POS)
    if r is None:
        return None
    final, ret, dd, shp, nt, nd, mtv, ser = r
    idx = sorted([dt for dt in B.G_all if pd.Timestamp(dt).year == year])
    vals = np.asarray(ser.values, dtype=float)
    assert len(vals) == len(idx), f"{year}: {len(vals)} values vs {len(idx)} dates"
    return dict(eq0=eq_start, final=final, ret=ret, dd=dd, shp=shp, nt=nt, nd=nd,
                mtv=mtv, ser=pd.Series(vals, index=pd.DatetimeIndex(idx)))


def month_matrix(years_data, title, note):
    print()
    print("=" * 100)
    print(f"{title}   ({note})")
    print("=" * 100)
    print(f"{'Year':<6}" + "".join(f"{m:>6}月" for m in range(1, 13)) + f"{'Year%':>9}{'Trades':>8}{'Tr/day':>8}")
    print("-" * 100)
    all_m = []
    for d in years_data:
        curve, y = d["ser"], d["ser"].index[0].year
        row = []
        for m in range(1, 13):
            mm = curve[curve.index.month == m]
            if len(mm) == 0:
                row.append(None); continue
            prev = curve[curve.index < mm.index[0]]
            base = prev.iloc[-1] if len(prev) else d["eq0"]
            row.append((mm.iloc[-1] / base - 1) * 100)
        all_m += [r for r in row if r is not None]
        print(f"{y:<6}" + "".join(("      -" if r is None else f"{r:>+6.1f}") for r in row)
              + f"{d['ret']:>+9.1f}{d['nt']:>8}{d['nt']/d['nd']:>8.1f}")
    mr = pd.Series(all_m)
    print(f"\n  months positive {(mr>0).mean()*100:.1f}% ({(mr>0).sum()}/{len(mr)}) | worst {mr.min():+.2f}% | best {mr.max():+.2f}% | mean {mr.mean():+.2f}%")


def rolling_within_year(years_data):
    print("\n  rolling windows computed WITHIN each year (no cross-year carry):")
    for w, nm in [(21, "1M"), (63, "3M"), (126, "6M"), (252, "12M")]:
        vals = []
        for d in years_data:
            r = d["ser"].pct_change().fillna(0)
            roll = r.rolling(w).apply(lambda x: (1 + x).prod() - 1).dropna()
            vals += list(roll.values)
        v = pd.Series(vals)
        if len(v):
            print(f"    {nm:>3}: positive {(v>0).mean()*100:5.1f}% ({(v>0).sum()}/{len(v)}) | min {v.min()*100:+.2f}%")


def daily_stats(curve):
    r = curve.pct_change().fillna(0)
    dd = ((curve - curve.cummax()) / curve.cummax()).min() * 100
    sh = r.mean() / r.std() * np.sqrt(243)
    return dd, sh, len(curve)


print("#" * 100)
print("# Gap Fade v13 - FINAL PERFORMANCE")
print("# live-exact config: k_model OFF, direction-balance OFF, min position 0.5%")
print("# liquidity floor = 5 x equity (one-way participation 5%). NO absolute capital cap.")
print("# entry gap SHORT +1.5% / LONG -5.0% market-adjusted | SL min(4%, limit-price-1tick) | TP 12%/20% | 13:20 flat")
print("# cost 0.2% x 1.7 discount = 0.109%/side | whole lots only | zero margin")
print("#" * 100)

# ---------------- D ----------------
rows = [series_for(4_500_000, y) for y in range(2014, 2027)]
rows = [d for d in rows if d]

print()
print("=" * 100)
print("D) EVERY YEAR STARTS AT 450wan  -  what 450wan of real trading looks like, year by year")
print("=" * 100)
print(f"{'Year':<6}{'Ret%':>9}{'MDD%':>8}{'Sharpe':>8}{'Tr/day':>8}{'PnL(wan)':>11}{'minTV(wan)':>12}{'fills':>7}")
print("-" * 100)
for d in rows:
    print(f"{d['ser'].index[0].year:<6}{d['ret']:>+9.1f}{d['dd']:>8.1f}{d['shp']:>8.2f}{d['nt']/d['nd']:>8.1f}"
          f"{(d['final']-4_500_000)/1e4:>11.1f}{d['mtv']/1e4:>12.0f}{d['nt']:>7}")
ret = [d["ret"] for d in rows]
print("-" * 100)
print(f"{'AVG':<6}{np.mean(ret):>+9.1f}{min(d['dd'] for d in rows):>8.1f}{np.mean([d['shp'] for d in rows]):>8.2f}"
      f"{np.mean([d['nt']/d['nd'] for d in rows]):>8.1f}{np.mean([(d['final']-4_500_000)/1e4 for d in rows]):>11.1f}")
print(f"\n  all 13 years positive: {all(r > 0 for r in ret)} | worst {min(ret):+.1f}% | best {max(ret):+.1f}% | worst MDD {min(d['dd'] for d in rows):.1f}%")
print(f"  total PnL 13y: {sum((d['final']-4_500_000)/1e4 for d in rows):,.0f} wan (each year independent)")
month_matrix(rows, "D) MONTHLY RETURNS %", "each year restarts at 450wan")
rolling_within_year(rows)

# ---------------- F ----------------
print()
print("#" * 100)
print("F) PURE COMPOUNDING, NO CAPITAL CAP  -  dynamic participation only, nothing withdrawn")
print("#" * 100)
print(f"{'Year':<6}{'Start(wan)':>12}{'Ret%':>9}{'End(wan)':>12}{'MDD%':>8}{'Sharpe':>8}{'Tr/day':>8}{'minTV(wan)':>12}{'fills':>7}")
print("-" * 100)
eq = 4_500_000
frows = []
for y in range(2014, 2027):
    d = series_for(eq, y)
    if d is None:
        continue
    print(f"{y:<6}{eq/1e4:>12.0f}{d['ret']:>+9.1f}{d['final']/1e4:>12.0f}{d['dd']:>8.1f}{d['shp']:>8.2f}"
          f"{d['nt']/d['nd']:>8.1f}{d['mtv']/1e4:>12.0f}{d['nt']:>7}")
    frows.append(d)
    eq = d["final"]
curve = pd.concat([d["ser"] for d in frows])
ny = len(set(curve.index.year))
cagr = (curve.iloc[-1] / 4_500_000) ** (1 / ny) - 1
dd, sh, ndays = daily_stats(curve)
print("-" * 100)
print(f"\n  450wan -> {curve.iloc[-1]/1e8:,.2f} yi over {ny}y | CAGR {cagr*100:.1f}% | daily-curve MDD {dd:.2f}% | Sharpe {sh:.2f} | {ndays} days")
month_matrix(frows, "F) MONTHLY RETURNS %", "pure compounding, no cap")
rolling_within_year(frows)

# ---------------- capacity ladder ----------------
print()
print("=" * 100)
print("CAPACITY LADDER - fixed capital per year (minTV = 5 x capital), live-exact")
print("=" * 100)
print(f"{'Capital(wan)':>13}{'minTV(wan)':>12}" + "".join(f"{y:>8}" for y in range(2014, 2027)) + f"{'AVG%':>8}{'worstMDD':>9}")
print("-" * 100)
for cap in [4_500_000, 10_000_000, 20_000_000, 50_000_000, 100_000_000, 200_000_000, 500_000_000]:
    rr = []
    for y in range(2014, 2027):
        d = series_for(cap, y)
        rr.append(d["ret"] if d else np.nan)
    d0 = series_for(cap, 2020)
    print(f"{cap/1e4:>13.0f}{d0['mtv']/1e4:>12.0f}" + "".join(f"{r:>+8.1f}" for r in rr)
          + f"{np.nanmean(rr):>+8.1f}{min(d['dd'] for d in [series_for(cap, y) for y in range(2014,2027)] if d):>9.1f}")
