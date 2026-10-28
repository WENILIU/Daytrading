"""Gap Fade v13 - full performance, NO capital cap (dynamic participation only).

Liquidity model: per-order dv_cap = 10% of T-1 dollar turnover (the only legal proxy at
09:00). The old 5x-equity pre-filter is OFF (PART=0) because it discarded tradeable names
long before impact bound. Position sizing / costs / exits are unchanged from the canonical
engine, so every number here is the same engine that produced STRATEGY_v13.md.

Reported per year: realised participation (notional / T-1 turnover). Once that pegs at the
dv_cap the run is at the model ceiling, not a forecast - the report says so explicitly.
"""
import sys, io, numpy as np, pandas as pd
sys.path.insert(0, ".")
import backtest_dyn_pure as B

LIVE = dict(use_k_model=False, use_ds=False, min_pos_pct=0.005)
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
OUT = io.open("full_report_nocap.txt", "w", encoding="utf-8")


def w(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    OUT.write(s + "\n")


def monthly(series):
    last = series.resample("ME").last()
    first = series.resample("ME").first()
    return ((last / first - 1) * 100).dropna()


def month_grid(mdict, label):
    w("\n" + "=" * 104)
    w(f"MONTHLY RETURNS pct - {label}")
    w("=" * 104)
    w(f"{'Year':<6}" + "".join(f"{m:>7}" for m in MONTHS) + f"{'Year%':>9}{'Neg':>5}")
    w("-" * 100)
    allv = []
    for y in sorted(mdict):
        v = mdict[y]
        allv += list(v.values)
        cells = "".join(f"{x:>7.1f}" for x in v.values) + " " * (7 * (12 - len(v)))
        yr = np.prod(1 + np.asarray(list(v.values)) / 100) * 100 - 100
        w(f"{y:<6}{cells}{yr:>9.1f}{int((v < 0).sum()):>5}")
    s = pd.Series(allv)
    w(f"\n  months {len(s)} | positive {(s > 0).mean() * 100:.1f}% | worst {s.min():.2f}% | "
      f"best {s.max():.2f}% | mean {s.mean():.2f}% | median {s.median():.2f}%")


def part_stats(parts):
    p = np.asarray(parts)
    if len(p) == 0:
        return (np.nan,) * 4
    return (np.median(p) * 100, np.percentile(p, 90) * 100, p.max() * 100, len(p))


def run_path(eq0, cap_eq, label):
    """Compound across years. cap_eq = withdraw everything above this (None = no cap)."""
    w("\n" + "=" * 104)
    w(label)
    w("=" * 104)
    w(f"{'Year':<6}{'Start(wan)':>11}{'Ret%':>8}{'End(wan)':>11}{'MDD%':>7}{'Sharpe':>8}"
      f"{'Tr/d':>6}{'Expo%':>7}{'Part%':>7}{'p90':>6}{'max':>6}{'Pegged':>8}")
    w("-" * 104)
    eq = eq0
    wd = 0.0
    ser, mdict, trace = [], {}, []
    for y in range(2014, 2027):
        col = []
        r = B.run_year(eq, y, None, collect=col, **LIVE)
        if r is None:
            continue
        final, ret, dd, shp, nt, nd, mtv, s, nu = r
        expo = np.median([c[3] / eq for c in col]) * 100 if col else 0.0
        allp = [x for c in col for x in c[4]]
        pm, p90, pmax, npart = part_stats(allp)
        peg = "YES" if np.isfinite(pm) and pm >= 9.0 else ""
        shown_end = final if cap_eq is None else min(final, cap_eq)
        w(f"{y:<6}{eq / 1e4:>11.0f}{ret:>8.1f}{shown_end / 1e4:>11.0f}{dd:>7.1f}{shp:>8.2f}"
          f"{nt / nd:>6.1f}{expo:>7.1f}{pm:>7.2f}{p90:>6.1f}{pmax:>6.1f}{peg:>8}")
        mdict[y] = monthly(s)
        ser.append(s)
        trace.append((y, eq, ret, final, dd))
        if cap_eq is not None and final > cap_eq:
            wd += final - cap_eq
            final = cap_eq
        eq = final
    w("-" * 104)
    rets = pd.concat([s.pct_change().fillna(0).iloc[1:] if len(s) > 1 else s.pct_change().fillna(0)
                      for s in ser]).sort_index()
    curve = eq0 * (1 + rets).cumprod()
    rr = curve.pct_change().dropna()
    dd = (curve - curve.cummax()) / curve.cummax()
    yrs = (curve.index[-1] - curve.index[0]).days / 365.25
    total = eq + wd
    cagr = (total / eq0) ** (1 / yrs) - 1
    w(f"\n  450wan -> {total / 1e8:.2f} yi over {yrs:.1f}y | CAGR {cagr * 100:.1f}% | "
      f"MDD {dd.min() * 100:.2f}% | Sharpe {rr.mean() / rr.std() * np.sqrt(243):.2f} | "
      f"Calmar {abs(cagr / dd.min()):.1f} | {len(curve)} days")
    if wd:
        w(f"  the path above is the TRADING SLEEVE held at {cap_eq / 1e4:,.0f}wan; "
          f"withdrawn above the cap {wd / 1e8:.2f} yi (cash, not compounded)")
    w(f"  worst drawdown trough {dd.idxmin().date()} (peak {curve.loc[:dd.idxmin()].idxmax().date()})")
    for n, lab in [(63, "3M"), (126, "6M"), (252, "12M")]:
        x = np.expm1(rr.rolling(n).sum().dropna()) * 100
        w(f"  rolling {lab:>3}: {len(x):4d} windows | {(x > 0).mean() * 100:5.1f}% positive | min {x.min():7.2f}%")
    return curve, mdict, trace


if __name__ == "__main__":
    B.rule["dv_cap"] = 0.10
    B.PART = 0.0
    w("Gap Fade v13 | engine backtest_dyn_pure.run_year | LIVE-EXACT sizing")
    w("  liquidity: per-order dv_cap 10% of T-1 turnover, 5x-equity pre-filter OFF")
    w("  sizing: base_pos x zt-aware multiplier, cap 25% of equity, zero margin, whole lots only")
    w("  cost 0.109%/side (fee 1.7 discount, no borrow), TP 7/12% by score, SL 5% capped by price limit, force close 13:25")
    w(f"  signal pool pred_q >= 0.20 | min_pos_pct {LIVE['min_pos_pct']:.3f} | k_model OFF | direction-balance OFF")

    nc, m_nc, tr_nc = run_path(4_500_000, None,
                               "NC) NO CAPITAL CAP - pure compounding, dynamic participation only")
    month_grid(m_nc, "NC uncapped compounding (path returns)")

    cap20, m_cap, _ = run_path(4_500_000, 20_000_000,
                               "C) COMPOUND then withdraw above 2000wan (the operating rule used so far)")
    month_grid(m_cap, "C capped at 2000wan (path returns)")

    # A: every year restarts at 450wan -> capital-independent strategy essence
    w("\n" + "=" * 104)
    w("A) EVERY YEAR RESTARTS AT 450wan - the strategy itself, independent of capital growth")
    w("=" * 104)
    w(f"{'Year':<6}{'Ret%':>8}{'MDD%':>7}{'Sharpe':>8}{'Tr/d':>6}{'PnL(wan)':>10}{'Part%':>7}{'p90':>6}{'Univ/d':>8}")
    w("-" * 78)
    m_a, rows = {}, []
    for y in range(2014, 2027):
        col = []
        r = B.run_year(4_500_000, y, None, collect=col, **LIVE)
        if r is None:
            continue
        final, ret, dd, shp, nt, nd, mtv, s, nu = r
        allp = [x for c in col for x in c[4]]
        pm, p90, pmax, _ = part_stats(allp)
        rows.append((y, ret, dd, shp, nt / nd, (final - 4.5e6) / 1e4))
        m_a[y] = monthly(s)
        w(f"{y:<6}{ret:>8.1f}{dd:>7.1f}{shp:>8.2f}{nt / nd:>6.1f}{(final - 4.5e6) / 1e4:>10.1f}{pm:>7.2f}{p90:>6.1f}{nu:>8}")
    w("-" * 78)
    w(f"  13y total PnL {sum(r[5] for r in rows):,.0f} wan | avg ret {np.mean([r[1] for r in rows]):.1f}% | "
      f"worst year {min(r[1] for r in rows):.1f}% | worst MDD {min(r[2] for r in rows):.1f}% | "
      f"avg Sharpe {np.mean([r[3] for r in rows]):.2f}")
    month_grid(m_a, "A restart-450wan-every-year (each year its own equity)")


    # fixed-capital ladder: what one size of money earns, and whether impact binds there
    w("\n" + "=" * 104)
    w("FIXED-CAPITAL LADDER - every year run independently at one FIXED size")
    w("=" * 104)
    w(f"{'Capital(wan)':<13}{'AvgRet%':>9}{'WorstYr%':>10}{'WorstMDD%':>11}{'AvgSharpe':>11}"
      f"{'PnL/yr(wan)':>13}{'Part%':>7}{'p90':>6}{'Pegged':>8}")
    w("-" * 92)
    for cap in [4_500_000, 10_000_000, 20_000_000, 30_000_000, 50_000_000, 100_000_000,
                200_000_000, 500_000_000, 1_000_000_000, 3_000_000_000]:
        rets, dds, shs, pnls, allp = [], [], [], [], []
        for y in range(2014, 2027):
            col = []
            r = B.run_year(cap, y, None, collect=col, **LIVE)
            if r is None:
                continue
            final, ret, dd, shp, nt, nd, mtv, _s, nu = r
            rets.append(ret); dds.append(dd); shs.append(shp)
            pnls.append((final - cap) / 1e4)
            allp += [x for c in col for x in c[4]]
        pm, p90, pmax, _ = part_stats(allp)
        peg = "YES" if np.isfinite(pm) and pm >= 9.0 else ""
        w(f"{cap / 1e4:<13.0f}{np.mean(rets):>9.1f}{min(rets):>10.1f}{min(dds):>11.1f}"
          f"{np.mean(shs):>11.2f}{np.mean(pnls):>13.1f}{pm:>7.2f}{p90:>6.1f}{peg:>8}")
    w("-" * 92)
    w("  Part% = median(order notional / that name T-1 dollar turnover), realised, not assumed.")
    w("  Pegged = half of all orders are already at the 10% dv_cap ceiling. Past that point the")
    w("  engine is placing its maximum allowed size in every name; the backtest cannot price the")
    w("  impact of that, so the number is a CEILING of the model, not a forecast.")

    # where does the uncapped path stop being a forecast
    w("\n" + "=" * 104)
    w("WHERE THE UNCAPPED PATH STOPS BEING A FORECAST")
    w("=" * 104)
    for y, e0, ret, e1, dd in tr_nc:
        w(f"  {y}  capital {e1 / 1e8:8.2f} yi")
    OUT.close()
