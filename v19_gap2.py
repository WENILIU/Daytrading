# -*- coding: utf-8 -*-
r"""Two things the first pass opened up.

1. The gap caps are live's SHORT 4 pct / LONG 8 pct, and widening SHORT to 6 pct
   improved BOTH windows and lowered MDD. The direction is monotone from 0.04 to
   0.06, so the cap has to be searched further before it is called.

2. lock_rate_up_250 is not a rate. v13_factors.py:97 builds it as
   rate(up_t, up_t, 250, 3) - numerator and denominator are the same mask - so
   the column is identically 1.0 for any name that touched 漲停 at least 3 times
   in 250 sessions and NaN otherwise. That is why every threshold from 0.50 down
   to 0.10 returned the same book: the filter was "has this stock ever touched
   the limit", a binary that removes 51.6 pct of the signals. The intended
   quantity is locked-over-touched, which has never been computed anywhere.

This script recomputes the real rate from the same price store and uses it only
as a filter. The model keeps the feature it was trained on; nothing here is
retraining, and that has to stay said out loud.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T
import v13_factors as F

CAP = T.CAP0
PIN = 0.00747
BRAKE = ((-0.008, .50), (-0.016, .25))
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08,
            spread=0.00105, nosl=True, brake=BRAKE, pin_penalty=PIN)


def sm(y):
    yr = y["yearly"]; ks = sorted(yr)
    v = [yr[k] / CAP * 100 for k in ks]

    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    return (sum(v) / len(v), avg(2014, 2021), avg(2022, 2026), y["mdd"], min(v),
            y["n_pin"], y["n_lockskip"], sum(yr.values()))


HDR = "%-32s %+6s %+8s %+8s %7s %7s %6s %6s %6s" % (
    "配置", "13yr", "2014-21", "2022-26", "MDD", "最差年", "鎖價筆", "跳過筆", "筆/日")
rows = []


def show(tag, **kw):
    y = T.run(**dict(base, **kw))
    a, o, r, m, w, np_, nl, tot = sm(y)
    flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ""
    print(("%-32s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %6d %6d %6.1f%s")
          % (tag, a, o, r, m, w, np_, nl, y["per_day"], flag), flush=True)
    rows.append(dict(tag=tag, all=a, old=o, recent=r, mdd=m, worst=w, n_pin=np_,
                     n_skip=nl, per_day=y["per_day"], total=tot))


print("=== A. gap 上限往更寬處掃（選 2014-2021，報 2022-2026）===", flush=True)
print(HDR, flush=True)
for s, l in ((0.06, 0.08), (0.07, 0.08), (0.08, 0.08), (None, 0.08),
             (0.06, 0.10), (0.06, None)):
    show("SHORT<=%s LONG=%s" % (s if s else "開", l if l else "開"),
         gap_max=s, gap_max_long=l)

# ---- the real lock rate ----
C = pd.read_pickle(F._sp("close")).astype(float)
H = pd.read_pickle(F._sp("high")).astype(float)
L = pd.read_pickle(F._sp("low")).astype(float)
PC = C.shift(1); valid = PC.notna() & (PC > 0)
tick = pd.DataFrame(np.select([PC.values < 10, PC.values < 100, PC.values < 500,
                               PC.values < 1000, PC.values < 5000],
                              [0.05, 0.1, 0.5, 1.0, 5.0], 10.0),
                    index=PC.index, columns=PC.columns)
LU = pd.DataFrame(np.floor(PC.values * 1.10 / tick.values) * tick.values,
                  index=PC.index, columns=PC.columns)
LD = pd.DataFrame(np.ceil(PC.values * 0.90 / tick.values) * tick.values,
                  index=PC.index, columns=PC.columns)
up_t = (H.values >= LU.values - 1e-9) & valid.values
up_l = (C.values >= LU.values - 1e-9) & valid.values
dn_t = (L.values <= LD.values + 1e-9) & valid.values
dn_l = (C.values <= LD.values + 1e-9) & valid.values


def mk(a):
    return pd.DataFrame(np.asarray(a, dtype=float), index=C.index, columns=C.columns)


def rate(n, d, win=250, mind=3):
    a = mk(n).rolling(win).sum(); b = mk(d).rolling(win).sum()
    return (a / b).where(b >= mind).shift(1)


up_rate = rate(up_l, up_t).values
dn_rate = rate(dn_l, dn_t).values
rp = {d: i for i, d in enumerate(C.index)}
cp = {c: j for j, c in enumerate(C.columns)}
vu = np.full(len(T.D), np.nan); vd = np.full(len(T.D), np.nan)
for k, (d, c) in enumerate(zip(T.D["date"].values, T.D["stock"].values)):
    i = rp.get(d); j = cp.get(c)
    if i is not None and j is not None:
        vu[k] = up_rate[i, j]; vd[k] = dn_rate[i, j]
T.D["lock_rate_up_250"] = vu
T.D["lock_rate_dn_250"] = vd
T.GROUPS = {d: g[~g["blocked"]] for d, g in T.D.groupby("date")}

sh = T.D.loc[T.D["direction"] == "SHORT", "lock_rate_up_250"].dropna()
lo = T.D.loc[T.D["direction"] == "LONG", "lock_rate_dn_250"].dropna()
print("\n真正的鎖板率（被鎖在漲停的次數 / 碰過漲停的次數，250 日，T-1）:", flush=True)
print("  SHORT 側 n=%d  p10=%.2f p50=%.2f p75=%.2f p90=%.2f"
      % (len(sh), sh.quantile(.1), sh.quantile(.5), sh.quantile(.75), sh.quantile(.9)), flush=True)
print("  LONG  側 n=%d  p10=%.2f p50=%.2f p75=%.2f p90=%.2f"
      % (len(lo), lo.quantile(.1), lo.quantile(.5), lo.quantile(.75), lo.quantile(.9)), flush=True)

print("\n=== B. 用真正的鎖板率過濾 ===", flush=True)
print(HDR, flush=True)
for lr in (0.95, 0.85, 0.70, 0.50, 0.30):
    show("真鎖板率 <= %.2f" % lr, max_lock_rate=lr)

pd.DataFrame(rows).to_csv("_gap2_lockfix.csv", index=False)
print("\nsaved _gap2_lockfix.csv", flush=True)
