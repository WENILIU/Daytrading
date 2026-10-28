"""Can "this name has not been day traded lately" replace the broker's nDayTrade flag?

Both are measured against the signals the strategy actually takes. The broker flag is
today's snapshot applied to 13 years, so its cost is an upper bound. The volume rule is
computed per date from T-1 exchange data, so it is a real pre-open filter that needs no
broker cache - but it measures market activity, not permission, so it is only ever allowed
to be a subset of the broker's answer.
"""
import json, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import backtest_dyn_pure as B

LIVE = dict(use_k_model=False, use_ds=False, min_pos_pct=0.005)
vol = pd.read_pickle("_dtvol_panel.pkl")
vol = vol.reindex(sorted(B.G_all, key=lambda d: pd.Timestamp(d)))
j = json.load(open("_dt_explain.json", encoding="utf-8"))
zeros = set(j["zeros"])
uni = {l.strip() for l in open("valid_stocks.txt", encoding="utf-8") if l.strip()}

def no_day_trade(n):
    """True when the exchange recorded no day-trade volume for the previous n sessions.
    shift(1) keeps it a T-1 fact. NaN counts as no volume: a code absent from the
    exchange's day-trade table is not being day traded."""
    return vol.fillna(0).rolling(n, min_periods=n).sum().shift(1) <= 0

rules = {f"zero day-trade volume, last {n} sessions": no_day_trade(n) for n in (5, 20)}
print("agreement with the broker's nDayTrade=0 list (today, %d codes):" % len(zeros))
for name, m in rules.items():
    today = m.iloc[-1]
    flagged = {c for c in m.columns if bool(today.get(c, False)) and c in uni}
    print(f"  {name:<40} flags {len(flagged):4d} | covers {len(flagged & zeros):3d}/{len(zeros)} "
          f"of the broker's 0 | false positives {len(flagged - zeros):3d}")

BASE = [0.0]

def run(label, mask=None):
    orig = B.G_all
    newG = {}
    for dt, sub in orig.items():
        d = pd.Timestamp(dt)
        if mask is None or d not in mask.index:
            newG[dt] = sub
            continue
        row = mask.loc[d]
        drop = np.array([bool(row.get(s, False)) for s in sub["stock"]], dtype=bool)
        newG[dt] = sub[~drop]
    B.G_all = newG
    tot = 0.0; rets = []; dds = []; shs = []; tpd = []
    for yr in range(2014, 2027):
        r = B.run_year(4_500_000, yr, None, **LIVE)
        if r is None:
            continue
        final, ret, dd, shp, nt, nd, mtv, s, nu = r
        tot += (final - 4.5e6) / 1e4; rets.append(ret); dds.append(dd); shs.append(shp); tpd.append(nt / nd)
    B.G_all = orig
    base = BASE[0] or tot
    BASE[0] = BASE[0] or tot
    print(f"  {label:<40} PnL {tot:>9,.0f} wan ({(tot - base) / base * 100:+6.2f}%) | "
          f"avg {np.mean(rets):>6.1f}% | worst yr {min(rets):>6.1f}% | "
          f"worst MDD {min(dds):>5.1f}% | Sharpe {np.mean(shs):.2f} | Tr/d {np.mean(tpd):>5.1f}")
    return tot

B.rule["dv_cap"] = 0.10
B.PART = 0.0
print("\nbacktest cost, 450wan restarted every year:")
run("as published")
for name, m in rules.items():
    run("+ " + name, m)
