"""Cost of honouring the broker's nDayTrade=0 list, measured honestly.

The list is TODAY'S broker cache, so applying it to 13 years is an approximation - it is
reported as an upper bound on the damage, not a per-date fact. Split into the part the
exchange rules already explain (full-cash-delivery) and the part they do not.
"""
import json, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import backtest_dyn_pure as B

LIVE = dict(use_k_model=False, use_ds=False, min_pos_pct=0.005)
panel = pd.read_pickle("_fcd_panel.pkl")
st = panel.stack(); st = st[st]
FCD = {(pd.Timestamp(d), s) for d, s in st.index}
j = json.load(open("_dt_explain.json", encoding="utf-8"))
zeros = set(j["zeros"])
fcd_today = set(j["fcd"])
unexplained = zeros - fcd_today
print(f"broker nDayTrade=0: {len(zeros)} | explained by full-cash-delivery today: {len(fcd_today)} "
      f"| unexplained: {len(unexplained)}")

def count(codes):
    n = 0
    for dt, sub in B.G_all.items():
        n += int(sub["stock"].isin(codes).sum())
    return n

print(f"signals touching nDayTrade=0 codes: {count(zeros)} / {sum(len(s) for s in B.G_all.values()):,} "
      f"({count(zeros)/sum(len(s) for s in B.G_all.values())*100:.2f}%)")
print(f"  of which the unexplained {len(unexplained)} codes: {count(unexplained)}")

def run(label, drop_codes=None, drop_fcd=False):
    orig = B.G_all
    newG = {}
    for dt, sub in orig.items():
        d = pd.Timestamp(dt)
        m = np.zeros(len(sub), dtype=bool)
        if drop_codes:
            m |= sub["stock"].isin(drop_codes).values
        if drop_fcd:
            m |= np.array([(d, s) in FCD for s in sub["stock"]], dtype=bool)
        newG[dt] = sub[~m]
    B.G_all = newG
    tot = 0.0; rets = []; dds = []; shs = []
    for yr in range(2014, 2027):
        r = B.run_year(4_500_000, yr, None, **LIVE)
        if r is None:
            continue
        final, ret, dd, shp, nt, nd, mtv, s, nu = r
        tot += (final - 4.5e6) / 1e4; rets.append(ret); dds.append(dd); shs.append(shp)
    B.G_all = orig
    print(f"  {label:<52} PnL {tot:>9,.0f} wan | avg {np.mean(rets):>6.1f}% | worst yr {min(rets):>6.1f}% "
          f"| worst MDD {min(dds):>5.1f}% | Sharpe {np.mean(shs):.2f}")
    return tot

B.rule["dv_cap"] = 0.10
B.PART = 0.0
t0 = run("as published")
t1 = run("+ full-cash-delivery (exchange, per-date)", drop_fcd=True)
t2 = run("+ broker nDayTrade=0 list (today snapshot, all 221)", drop_codes=zeros)
t3 = run("+ both", drop_codes=zeros, drop_fcd=True)
print(f"\n  deltas vs published: FCD {(t1-t0)/t0*100:+.2f}% | broker-0 {(t2-t0)/t0*100:+.2f}% | both {(t3-t0)/t0*100:+.2f}%")
