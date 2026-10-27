"""Pure dynamic min_turnover = 5*equity (5% participation, no floor). Each year starts at 4.5M."""
import pandas as pd, numpy as np, warnings
warnings.filterwarnings("ignore")
import sys; sys.path.insert(0, ".")
from v13_sizing import lots_for

df_all = pd.read_pickle("signals_v13.pkl")
df_all = df_all[df_all["pred"].notna()].copy()
df_all["stock"] = df_all["stock"].astype(str)
df_all = df_all[df_all["pred_q"] >= 0.20]

tr = {}
for direc in ["SHORT","LONG"]:
    s = df_all[df_all["direction"]==direc].sort_values("date")
    s["t30"] = s["p"].rolling(30, min_periods=30).mean().shift(1)
    for dt, x in zip(s["date"], s["t30"].values):
        tr[(dt, direc)] = x

G_all = {dt: sub for dt, sub in df_all.groupby("date")}

BP1, BP2, M1, M2, MP = 0.015, 0.045, 10.0, 2.5, 0.25
rule = {"name":"t","scale":1.0,"cap":None,"cap_pct":0.25,"floor_lot":None,
        "floor_lot_pct":0.25,"dv_cap":None,"min_turnover_factor":None}

def run_year(eq_start, year):
    """Dynamic min_turnover = max(20M, 5*equity) applied per-signal."""
    min_tv = 5.0 * eq_start  # pure dynamic: 5% participation, no floor
    
    year_dates = [dt for dt in G_all if pd.Timestamp(dt).year == year]
    if len(year_dates) < 50: return None
    
    eq = eq_start; eqs = [eq_start]; n_total = 0
    for dt in sorted(year_dates):
        sub = G_all[dt].copy()
        # Apply dynamic min_turnover filter
        sub = sub[sub["prev_turnover"] >= min_tv]
        if len(sub) == 0:
            eqs.append(eq); continue
        sub = sub.sort_values("pred", ascending=False)
        
        peak = max(eqs); cdd = (eq-peak)/peak
        rs = 0.12 if cdd < -0.012 else (0.3 if cdd < -0.006 else 1.0)
        zd = sub["zt_dist"].values
        zm = np.where(zd < BP1, M1, np.where(zd < BP2, M2, 1.0))
        p_pred = np.asarray(sub["pred"].values, dtype=float)
        kM = np.where(np.isfinite(p_pred), np.clip(0.5+np.nan_to_num(p_pred)/0.02, 0, 2), 1.0)
        p30 = np.array([tr.get((dt, x), np.nan) for x in sub["direction"]], dtype=float)
        kT = np.where(np.isnan(p30), 1.0, np.clip(0.5+p30/0.02, 0, 2.0))
        short_pct = (sub["direction"]=="SHORT").mean()
        ds_val = 0.5 if short_pct > 0.8 or short_pct < 0.2 else 1.0
        weights = np.minimum(np.asarray(sub["base_pos"].values, dtype=float) * zm * ds_val * rs * kM * kT, MP)
        o = np.argsort(-np.nan_to_num(p_pred, nan=-99))
        weights = weights[o]
        pn = np.asarray(sub["p"].values, dtype=float)[o]
        pr = np.asarray(sub["entry"].values, dtype=float)[o]
        dv = np.asarray(sub["prev_turnover"].values, dtype=float)[o]
        rem = eq; day_pnl = 0.0; n_exec = 0
        for i in range(len(weights)):
            if weights[i] <= 0: continue
            n = lots_for(rule, weights[i], pr[i], rem, dv[i], capital=eq)
            if n == 0: continue
            notional = n * 1000 * pr[i]
            if notional > rem: continue
            rem -= notional; day_pnl += notional * pn[i]; n_exec += 1
        eq += day_pnl; eqs.append(eq); n_total += n_exec
    
    eq_s = pd.Series(eqs[1:])
    ret = eq_s.pct_change().fillna(0)
    yr_ret = (eq_s.iloc[-1] / eq_start - 1) * 100
    yr_dd = ((eq_s - eq_s.cummax()) / eq_s.cummax()).min() * 100
    shp = ret.mean() / ret.std() * np.sqrt(243) if ret.std() > 0 else 0
    return eq_s.iloc[-1], yr_ret, yr_dd, shp, n_total, len(year_dates)

# Scenario: each year 4.5M
print(f"{'='*75}")
print(f"每年 450萬 | min_turnover = max(2000萬, 5x淨值) = 2000萬")
print(f"{'='*75}")
print(f"{'Year':<6} {'報酬%':<8} {'MDD%':<7} {'Sharpe':<7} {'筆/日':<6} {'PnL(萬)':<9} {'年末(萬)'}")
print("-"*60)

total_pnl = 0
for y in range(2014, 2027):
    result = run_year(4_500_000, y)
    if result is None: continue
    final, ret, dd, shp, nt, nd = result
    pnl = (final - 4_500_000) / 10000
    total_pnl += pnl
    print(f"{y:<6} {ret:<8.1f} {dd:<7.1f} {shp:<7.2f} {nt/nd:<6.1f} {pnl:<9.1f} {final/10000:.0f}")

print(f"\n  13年總獲利: {total_pnl:,.0f} 萬 | 平均年: {total_pnl/13:,.0f} 萬")

# Also: compound to 20M then cap
print(f"\n{'='*75}")
print(f"複利到2000萬後固定 | min_turnover = max(2000萬, 5x淨值)")
print(f"{'='*75}")
print(f"{'Year':<6} {'年初(萬)':<9} {'報酬%':<8} {'年末(萬)':<9} {'出金(萬)':<9} {'累計出金(萬)':<11} {'MDD%':<6} {'min_tv(萬)'}")
print("-"*75)

eq = 4_500_000; total_wd = 0
for y in range(2014, 2027):
    min_tv = 5.0 * eq  # pure dynamic: 5% participation, no floor
    result = run_year(eq, y)
    if result is None: continue
    final, ret, dd, shp, nt, nd = result
    withdrawn = 0
    if final > 20_000_000:
        withdrawn = final - 20_000_000
        final = 20_000_000
        total_wd += withdrawn
    print(f"{y:<6} {eq/10000:<9.0f} {ret:<8.1f} {final/10000:<9.0f} {withdrawn/10000:<9.0f} {total_wd/10000:<11.0f} {dd:<6.1f} {min_tv/10000:.0f}")
    eq = final

total_wealth = eq + total_wd
print(f"\n  交易資金: {eq/10000:,.0f}萬 | 出金: {total_wd/10000:,.0f}萬 | 總財富: {total_wealth/1e8:.2f}億")
