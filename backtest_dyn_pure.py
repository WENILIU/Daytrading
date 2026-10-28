"""Gap Fade v13 capital-capacity backtest (CANONICAL ENTRY POINT).

Position sizing / liquidity floor = pure dynamic participation: min_turnover = 5 x equity,
i.e. one-way participation always 5 pct at any capital. No absolute floors anywhere.
Scenario A: every year restarts at 4.5M. Scenario C: compound, withdraw above 20M.
Scenario B (20M floor) is kept only as a control - it never binds, results are identical.
"""
import pandas as pd, numpy as np, warnings, sys
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from v13_sizing import lots_for

df_all = pd.read_pickle("signals_v13.pkl")
df_all = df_all[df_all["pred"].notna()].copy()
df_all["stock"] = df_all["stock"].astype(str)
df_all = df_all[df_all["pred_q"] >= 0.20]

tr = {}
for direc in ["SHORT", "LONG"]:
    s = df_all[df_all["direction"] == direc].sort_values("date")
    s["t30"] = s["p"].rolling(30, min_periods=30).mean().shift(1)
    for dt, x in zip(s["date"], s["t30"].values):
        tr[(dt, direc)] = x

G_all = {dt: sub for dt, sub in df_all.groupby("date")}

BP1, BP2, M1, M2, MP = 0.015, 0.045, 10.0, 2.5, 0.25
rule = {"name": "t", "scale": 1.0, "cap": None, "cap_pct": 0.25, "floor_lot": None,
        "floor_lot_pct": 0.25, "dv_cap": None, "min_turnover_factor": None}
PART = 5.0  # participation factor: min_turnover = PART * equity  ->  0.25/PART = 5% participation


def run_year(eq_start, year, floor=None, use_k_model=True, use_ds=True, min_pos_pct=0.0, collect=None):
    min_tv = PART * eq_start
    if floor is not None:
        min_tv = max(floor, min_tv)
    yd = [dt for dt in G_all if pd.Timestamp(dt).year == year]
    if len(yd) < 50:
        return None
    eq = eq_start; eqs = [eq_start]; n_total = 0; n_univ = []
    for dt in sorted(yd):
        sub = G_all[dt]
        sub = sub[sub["prev_turnover"] >= min_tv]
        n_univ.append(len(sub))
        if len(sub) == 0:
            if collect is not None:
                collect.append((dt, 0, 0.0, 0.0))
            eqs.append(eq); continue
        sub = sub.sort_values("pred", ascending=False)
        peak = max(eqs); cdd = (eq - peak) / peak
        rs = 0.12 if cdd < -0.012 else (0.3 if cdd < -0.006 else 1.0)
        zd = sub["zt_dist"].values
        zm = np.where(zd < BP1, M1, np.where(zd < BP2, M2, 1.0))
        p_pred = np.asarray(sub["pred"].values, dtype=float)
        if use_k_model:
            kM = np.where(np.isfinite(p_pred), np.clip(0.5 + np.nan_to_num(p_pred) / 0.02, 0, 2), 1.0)
        else:
            kM = np.ones(len(p_pred))
        p30 = np.array([tr.get((dt, x), np.nan) for x in sub["direction"]], dtype=float)
        kT = np.where(np.isnan(p30), 1.0, np.clip(0.5 + p30 / 0.02, 0, 2.0))
        sp = (sub["direction"] == "SHORT").mean()
        ds_val = (0.5 if sp > 0.8 or sp < 0.2 else 1.0) if use_ds else 1.0
        base = np.asarray(sub["base_pos"].values, dtype=float)
        w = np.minimum(base * zm * ds_val * rs * kM * kT, MP)
        if min_pos_pct > 0:
            w = np.where(w >= min_pos_pct, w, 0.0)  # live: skip designs too small for 1 zhang
        o = np.argsort(-np.nan_to_num(p_pred, nan=-99))
        w = w[o]
        pn = np.asarray(sub["p"].values, dtype=float)[o]
        pr = np.asarray(sub["entry"].values, dtype=float)[o]
        dv = np.asarray(sub["prev_turnover"].values, dtype=float)[o]
        rem = eq; day_pnl = 0.0; n_exec = 0; gross = 0.0; biggest = 0.0
        for i in range(len(w)):
            if w[i] <= 0:
                continue
            n = lots_for(rule, w[i], pr[i], rem, dv[i], capital=eq)
            if n == 0:
                continue
            notional = n * 1000 * pr[i]
            if notional > rem:
                continue
            rem -= notional; day_pnl += notional * pn[i]; n_exec += 1
            gross += notional; biggest = max(biggest, notional)
        if collect is not None:
            collect.append((dt, n_exec, biggest, gross))
        eq += day_pnl; eqs.append(eq); n_total += n_exec
    eq_s = pd.Series(eqs[1:], index=pd.to_datetime(sorted(yd)))
    ret = eq_s.pct_change().fillna(0)
    yr_ret = (eq_s.iloc[-1] / eq_start - 1) * 100
    yr_dd = ((eq_s - eq_s.cummax()) / eq_s.cummax()).min() * 100
    shp = ret.mean() / ret.std() * np.sqrt(243) if ret.std() > 0 else 0
    return (eq_s.iloc[-1], yr_ret, yr_dd, shp, n_total, len(yd), min_tv, eq_s,
            int(np.median(n_univ)) if n_univ else 0)


def scenario_each_year(floor, label, use_k_model=True, use_ds=True, min_pos_pct=0.0):
    print("=" * 78)
    print(label)
    print("=" * 78)
    print(f"{'Year':<6} {'Ret%':<8} {'MDD%':<7} {'Sharpe':<7} {'Tr/d':<6} {'PnL(wan)':<9} {'minTV(wan)':<11} {'Univ'}")
    print("-" * 72)
    tot = 0.0; rows = []
    for y in range(2014, 2027):
        r = run_year(4_500_000, y, floor, use_k_model, use_ds, min_pos_pct)
        if r is None:
            continue
        final, ret, dd, shp, nt, nd, mtv, _ser, nu = r
        pnl = (final - 4_500_000) / 1e4
        tot += pnl
        rows.append((y, ret, dd, shp, nt / nd, pnl, mtv))
        print(f"{y:<6} {ret:<8.1f} {dd:<7.1f} {shp:<7.2f} {nt/nd:<6.1f} {pnl:<9.1f} {mtv/1e4:<11.0f} {nu}")
    print(f"\n  13y total PnL: {tot:,.0f} wan | avg/yr {tot/len(rows):,.0f} wan | avg ret {np.mean([r[1] for r in rows]):.1f}% | worst {min(r[1] for r in rows):.1f}% | worst MDD {min(r[2] for r in rows):.1f}%")
    print(f"  avg Sharpe {np.mean([r[3] for r in rows]):.2f}")
    return rows


def scenario_compound(floor, cap_eq, label, use_k_model=True, use_ds=True, min_pos_pct=0.0):
    print()
    print("=" * 78)
    print(label)
    print("=" * 78)
    print(f"{'Year':<6} {'Start(wan)':<11} {'Ret%':<8} {'End(wan)':<10} {'Withdraw':<10} {'CumWD':<8} {'MDD%':<7} {'minTV(wan)':<11} {'Univ/d'}")
    print("-" * 88)
    eq = 4_500_000; wd = 0; _trace = []; _series = []
    for y in range(2014, 2027):
        r = run_year(eq, y, floor, use_k_model, use_ds, min_pos_pct)
        if r is None:
            continue
        final, ret, dd, shp, nt, nd, mtv, ser, nu = r
        if cap_eq is None:
            _series.append(ser)
        w = 0
        if cap_eq is not None and final > cap_eq:
            w = final - cap_eq; final = cap_eq; wd += w
        print(f"{y:<6} {eq/1e4:<11.0f} {ret:<8.1f} {final/1e4:<10.0f} {w/1e4:<10.0f} {wd/1e4:<8.0f} {dd:<7.1f} {mtv/1e4:.0f} {nu}")
        _trace.append((y, eq, ret, final, dd, mtv, nu))
        eq = final
    print(f"\n  trading capital {eq/1e4:,.0f} wan | withdrawn {wd/1e4:,.0f} wan | TOTAL {((eq+wd)/1e8):.2f} yi")
    yrs = len(_trace)
    if yrs:
        cagr = ((eq + wd) / 4_500_000) ** (1 / yrs) - 1
        peak = 4_500_000; mdd = 0.0
        for y, e0, r, e1, dd, mtv, nu in _trace:
            peak = max(peak, e1); mdd = min(mdd, (e1 - peak) / peak * 100)
        print(f"  PATH CAGR {cagr*100:.1f}% over {yrs}y | worst year {min(t[2] for t in _trace):.1f}% | path MDD {mdd:.1f}%")
        print(f"  final equity {eq/1e8:.2f} yi (no withdrawal)")
        if _series:
            chain = pd.concat(_series)
            curve = 4_500_000 * (1 + chain.pct_change().fillna(0)).cumprod()
            dd = ((curve - curve.cummax()) / curve.cummax()).min() * 100
            r = curve.pct_change().dropna()
            sh = r.mean() / r.std() * np.sqrt(243)
            print(f"  DAILY-CURVE path MDD {dd:.2f}% | Sharpe {sh:.2f} | {len(curve)} trading days")


if __name__ == "__main__":
    scenario_each_year(None, "A) PURE DYNAMIC participation 5% from day one (minTV = 5 x equity, NO floor)")
    scenario_each_year(20_000_000, "B) WITH 2000wan floor (previous version)")
    scenario_compound(None, 20_000_000, "C) PURE DYNAMIC | compound then withdraw above 2000wan")

    scenario_each_year(None, "D) LIVE-EXACT config (k_model OFF, direction-balance OFF, min_pos_pct 0.5 pct)",
                     use_k_model=False, use_ds=False, min_pos_pct=0.005)
    scenario_compound(None, 20_000_000, "E) LIVE-EXACT | compound then withdraw above 2000wan",
                      use_k_model=False, use_ds=False, min_pos_pct=0.005)
    scenario_compound(None, None, "F) LIVE-EXACT | PURE COMPOUNDING, no cap (dynamic participation only)",
                      use_k_model=False, use_ds=False, min_pos_pct=0.005)
