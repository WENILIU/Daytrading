"""What excluding full-cash-delivery names costs the strategy.

_fcd_panel.pkl is the exchange flag inverted at cache time: True = the stock IS
full-cash-delivery that day (24-64 names/day, 2014-01-02..2026-10-28). Full-cash-delivery
names cannot be day traded; all 29 of today's land in the broker's nDayTrade=0 bucket.

Only B.G_all is swapped - B.tr (the 30-day direction return feeding kT) stays as published,
so the delta measures the executable-universe change alone, not a model change.
"""
import io, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import backtest_dyn_pure as B

LIVE = dict(use_k_model=False, use_ds=False, min_pos_pct=0.005)
panel = pd.read_pickle("_fcd_panel.pkl")
st = panel.stack()
st = st[st]
FCD = {(pd.Timestamp(d), s) for d, s in st.index}
print(f"full-cash-delivery (date, code) pairs: {len(FCD):,} over {panel.shape[0]} days "
      f"({len(FCD)/panel.shape[0]:.0f}/day)")

n_sig = n_fcd = 0
for dt, sub in B.G_all.items():
    d = pd.Timestamp(dt)
    hit = np.array([(d, s) in FCD for s in sub["stock"]], dtype=bool)
    n_sig += len(sub); n_fcd += int(hit.sum())
print(f"signal pool {n_sig:,} rows | full-cash-delivery on the signal date: {n_fcd} ({n_fcd/n_sig*100:.2f}%)")

def run(label, swap):
    orig = B.G_all
    if swap:
        newG = {}
        for dt, sub in orig.items():
            d = pd.Timestamp(dt)
            newG[dt] = sub[~np.array([(d, s) in FCD for s in sub["stock"]], dtype=bool)]
        B.G_all = newG
    rows, tot = [], 0.0
    for yr in range(2014, 2027):
        r = B.run_year(4_500_000, yr, None, **LIVE)
        if r is None:
            continue
        final, ret, dd, shp, nt, nd, mtv, s, nu = r
        rows.append((yr, ret, dd, shp, nt / nd, (final - 4.5e6) / 1e4))
        tot += (final - 4.5e6) / 1e4
    B.G_all = orig
    print(f"\n{label}")
    print(f"{'Year':<6}{'Ret%':>8}{'MDD%':>8}{'Sharpe':>8}{'Tr/d':>7}{'PnL(wan)':>11}")
    for yr, ret, dd, shp, tpd, pnl in rows:
        print(f"{yr:<6}{ret:>8.1f}{dd:>8.1f}{shp:>8.2f}{tpd:>7.1f}{pnl:>11.1f}")
    m = np.array([[r[1], r[2], r[3], r[4]] for r in rows])
    print(f"  13y PnL {tot:,.0f} wan | avg {m[:,0].mean():.1f}% | worst yr {m[:,0].min():.1f}% | "
          f"worst MDD {m[:,1].min():.1f}% | avg Sharpe {m[:,2].mean():.2f} | avg Tr/d {m[:,3].mean():.1f}")
    return rows, tot

B.rule["dv_cap"] = 0.10
B.PART = 0.0
base, tot0 = run("BEFORE (as published: no full-cash-delivery exclusion)", False)
after, tot1 = run("AFTER (full-cash-delivery excluded per-date)", True)
print(f"\n  delta 13y PnL {tot1 - tot0:+,.0f} wan ({(tot1 - tot0) / tot0 * 100:+.2f}%)")
d = {a[0]: a[1] - b[1] for a, b in zip(after, base)}
worst = min(d, key=d.get)
print(f"  worst single-year change: {worst} {d[worst]:+.1f}pp | best {max(d, key=d.get)} {max(d.values()):+.1f}pp")
