# -*- coding: utf-8 -*-
r"""The lock rate that was supposed to exist, computed without pandas rolling.

v13_factors.py:97 builds lock_rate_up_250 as rate(up_t, up_t, 250, 3): numerator
and denominator are the same mask, so the column is 1.0 for any name that touched
漲停 at least 3 times in 250 sessions and NaN otherwise. The intended quantity is
locked-over-touched. The first attempt at the real rate died with
_ArrayMemoryError - pandas rolling materialises a full float64 frame per call and
v13_target already holds the signal table and two executability panels.

This version keeps the masks as bool and does the 250-day window sum with a
cumsum in float32, which costs one 54 MB array per mask instead of a chain of
float64 frames. The rate is used only as a filter; the model keeps the feature it
was trained on.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T
import v13_factors as F

CAP = T.CAP0
PIN = 0.00747
BRAKE = ((-0.008, .50), (-0.016, .25))
W, MIND = 250, 3


def window_rate(num, den):
    """sum(num, W) / sum(den, W) where sum(den, W) >= MIND, else NaN."""
    n, m = num.shape
    out = np.full((n, m), np.nan, dtype="float32")
    cn = np.cumsum(num, axis=0, dtype="float32")
    cd = np.cumsum(den, axis=0, dtype="float32")
    z = np.zeros((1, m), dtype="float32")
    sn = cn[W - 1:] - np.vstack([z, cn[:-W]])
    sd = cd[W - 1:] - np.vstack([z, cd[:-W]])
    ok = sd >= MIND
    r = np.where(ok, sn / np.where(sd > 0, sd, 1.0), np.nan).astype("float32")
    out[W - 1:] = r
    del cn, cd, sn, sd, ok, r
    return out


def load(name):
    df = pd.read_pickle(F._sp(name))
    v = np.asarray(df.values, dtype="float64")
    del df
    return v


idx = pd.read_pickle(F._sp("close")).index
cols = np.asarray([str(c) for c in pd.read_pickle(F._sp("close")).columns])
C = load("close"); H = load("high"); L = load("low")
PC = np.empty_like(C); PC[0] = np.nan; PC[1:] = C[:-1]
valid = np.isfinite(PC) & (PC > 0)
tick = np.select([PC < 10, PC < 100, PC < 500, PC < 1000, PC < 5000],
                 [0.05, 0.1, 0.5, 1.0, 5.0], 10.0)
LU = np.floor(PC * 1.10 / tick) * tick
LD = np.ceil(PC * 0.90 / tick) * tick
up_t = (H >= LU - 1e-9) & valid
up_l = (C >= LU - 1e-9) & valid
dn_t = (L <= LD + 1e-9) & valid
dn_l = (C <= LD + 1e-9) & valid
del C, H, L, PC, tick, LU, LD, valid
up_rate = window_rate(up_l, up_t)
dn_rate = window_rate(dn_l, dn_t)
del up_t, up_l, dn_t, dn_l

# the panel is shifted one day so a 09:00 decision only sees T-1
up_rate = np.vstack([np.full((1, len(cols)), np.nan, dtype="float32"), up_rate[:-1]])
dn_rate = np.vstack([np.full((1, len(cols)), np.nan, dtype="float32"), dn_rate[:-1]])

rp = {d: i for i, d in enumerate(idx)}
cp = {c: j for j, c in enumerate(cols)}
vu = np.full(len(T.D), np.nan); vd = np.full(len(T.D), np.nan)
for k, (d, c) in enumerate(zip(T.D["date"].values, T.D["stock"].values)):
    i = rp.get(d); j = cp.get(str(c))
    if i is not None and j is not None:
        vu[k] = up_rate[i, j]; vd[k] = dn_rate[i, j]
T.D["lock_rate_up_250"] = vu
T.D["lock_rate_dn_250"] = vd
T.GROUPS = {d: g[~g["blocked"]] for d, g in T.D.groupby("date")}
print("patched. resolved SHORT %d / LONG %d"
      % (int(np.isfinite(vu).sum()), int(np.isfinite(vd).sum())), flush=True)

sh = pd.Series(vu[T.D["direction"].values == "SHORT"]).dropna()
lo = pd.Series(vd[T.D["direction"].values == "LONG"]).dropna()
print("真正的鎖板率（250 日，T-1）", flush=True)
print("  SHORT 側 n=%d  p10=%.2f p50=%.2f p75=%.2f p90=%.2f"
      % (len(sh), sh.quantile(.1), sh.quantile(.5), sh.quantile(.75), sh.quantile(.9)), flush=True)
print("  LONG  側 n=%d  p10=%.2f p50=%.2f p75=%.2f p90=%.2f"
      % (len(lo), lo.quantile(.1), lo.quantile(.5), lo.quantile(.75), lo.quantile(.9)), flush=True)

base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08,
            spread=0.00105, nosl=True, brake=BRAKE, pin_penalty=PIN)
HDR = "%-26s %+6s %+8s %+8s %7s %7s %6s %6s %6s" % (
    "配置", "13yr", "2014-21", "2022-26", "MDD", "最差年", "鎖價筆", "跳過筆", "筆/日")
rows = []
print("\n" + HDR, flush=True)
y = T.run(**base)


def report(tag, y):
    yr = y["yearly"]; ks = sorted(yr)
    v = [yr[k] / CAP * 100 for k in ks]

    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    a, o, r, m, w = (sum(v) / len(v), avg(2014, 2021), avg(2022, 2026),
                     y["mdd"], min(v))
    flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ""
    print("%-26s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %6d %6d %6.1f%s"
          % (tag, a, o, r, m, w, y["n_pin"], y["n_lockskip"], y["per_day"], flag), flush=True)
    rows.append(dict(tag=tag, all=a, old=o, recent=r, mdd=m, worst=w,
                     n_pin=y["n_pin"], n_skip=y["n_lockskip"], per_day=y["per_day"]))


report("基準（不過濾）", y)
for lr in (0.95, 0.85, 0.70, 0.50, 0.30):
    report("真鎖板率 <= %.2f" % lr, T.run(**dict(base, max_lock_rate=lr)))
pd.DataFrame(rows).to_csv("_lock_true.csv", index=False)
print("saved _lock_true.csv", flush=True)
