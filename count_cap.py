"""What actually caps the trade count? candidates vs sized-ok vs executed."""
import pandas as pd, numpy as np, warnings, sys
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from v13_sizing import lots_for

df = pd.read_pickle("signals_v13.pkl")
df = df[df["pred"].notna()].copy()
df = df[df["pred_q"] >= 0.20]
G = {dt: s for dt, s in df.groupby("date")}

BP1, BP2, M1, M2, MP = 0.015, 0.045, 10.0, 2.5, 0.25
MIN_POS = 0.005
rule = {"name": "t", "scale": 1.0, "cap": None, "cap_pct": 0.25, "floor_lot": None,
        "floor_lot_pct": 0.25, "dv_cap": None, "min_turnover_factor": None}

rows = []
for dt in sorted(G):
    y = pd.Timestamp(dt).year
    if y < 2014:
        continue
    eq = 4_500_000
    min_tv = 5.0 * eq
    sub = G[dt]
    n_raw = len(sub)
    sub = sub[(sub["prev_turnover"] >= min_tv) & (sub["entry"] >= 30)]
    n_liq = len(sub)
    if n_liq == 0:
        rows.append((dt, n_raw, 0, 0, 0, 1.0)); continue
    zd = sub["zt_dist"].values
    zm = np.where(zd < BP1, M1, np.where(zd < BP2, M2, 1.0))
    base = np.asarray(sub["base_pos"].values, dtype=float)
    w = np.minimum(base * zm * 1.0 * 1.0, MP)          # k_model off, ds off, dd off (fresh day)
    o = np.argsort(-np.asarray(sub["pred"].values, dtype=float))
    w = w[o]
    pr = np.asarray(sub["entry"].values, dtype=float)[o]
    dv = np.asarray(sub["prev_turnover"].values, dtype=float)[o]
    n_sized = int((w >= MIN_POS).sum())
    rem = eq; n_exec = 0; blocked_by_cash = 0
    for i in range(len(w)):
        if w[i] < MIN_POS:
            continue
        n = lots_for(rule, w[i], pr[i], rem, dv[i], capital=eq)
        if n == 0:
            if w[i] * eq > rem:
                blocked_by_cash += 1
            continue
        notional = n * 1000 * pr[i]
        if notional > rem:
            blocked_by_cash += 1
            continue
        rem -= notional; n_exec += 1
    rows.append((dt, n_raw, n_liq, n_sized, n_exec, rem / eq))

R = pd.DataFrame(rows, columns=["date", "n_raw", "n_liq", "n_sized", "n_exec", "cash_left"])
R["year"] = pd.to_datetime(R["date"]).dt.year
g = R.groupby("year").agg(raw=("n_raw", "mean"), after_liq=("n_liq", "mean"),
                          sized=("n_sized", "mean"), executed=("n_exec", "mean"),
                          cash_left=("cash_left", "mean"),
                          days_no_cash=("cash_left", lambda x: (x < 0.02).mean()))
print("per-day averages, equity reset to 4.5M each day (isolates the count question)")
print(g.round(2).to_string())
print()
tot = R[["n_raw", "n_liq", "n_sized", "n_exec"]].mean()
print("ALL YEARS per-day mean:", dict(tot.round(2)))
print("share of sized candidates that got funded: %.1f%%" % (100 * R["n_exec"].sum() / max(R["n_sized"].sum(), 1)))
print("days where cash ran out (<2%% left): %.1f%%" % (100 * (R["cash_left"] < 0.02).mean()))
print("max candidates in a single day:", int(R["n_sized"].max()))
q = R["n_exec"].quantile([0.5, 0.9, 0.99, 1.0]).to_dict()
print("executed/day p50=%.0f p90=%.0f p99=%.0f max=%.0f" % (q[0.5], q[0.9], q[0.99], q[1.0]))
print("days with >15 executed: %.2f%%" % (100 * (R["n_exec"] > 15).mean()))
print("days with >20 executed: %.2f%%" % (100 * (R["n_exec"] > 20).mean()))
