# -*- coding: utf-8 -*-
"""Stage G: the last size knob (per-order share of the book) and a finer brake grid.

Stage B showed the participation cap is not binding. cap_pct is the other thing
that limits one order, so it has to be measured before the size question can be
closed. The brake grid is refined between 50/25 (MDD -4.60, in budget) and 60/35
(MDD -6.15, out) because the frontier there is steep and the -5.0 line sits in
the middle of it.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
SHIP = dict(brake=((-0.006, 0.30), (-0.012, 0.12)), liq=0.10, gap_max=0.04,
            gap_max_long=0.08, exposure=1.00, spread=T.SPREAD)
T1, T2 = -0.006, -0.012
MDD_FLOOR = -5.0


def ev(name, **over):
    cfg = dict(SHIP); cfg.update(over)
    r = T.run(**cfg)
    y = r["yearly"]; yrs = sorted(y)
    def win(lo, hi):
        s = [y[k] / CAP0 * 100 for k in yrs if lo <= k <= hi]
        return sum(s) / len(s) if s else float("nan")
    rets = [y[k] / CAP0 * 100 for k in yrs]
    return dict(name=name, all13=np.mean(rets), w0814=win(2014, 2021),
                w2226=win(2022, 2026), y26=y[2026] / CAP0 * 100, mdd=r["mdd"],
                worst=min(rets), per_day=r["per_day"], part90=r["part90"],
                brake=r["brake_pct"], ok=r["mdd"] >= MDD_FLOOR)


def show(rows, title):
    print("\n" + "=" * 112); print(title); print("=" * 112)
    print("  %-40s %7s %7s %7s %7s %7s %7s %6s %6s %5s"
          % ("設定", "13yr", "14-21", "22-26", "2026", "最差年", "MDD",
             "筆/日", "part90", "煞車%"))
    for r in sorted(rows, key=lambda x: -x["w2226"]):
        print("  %-40s %+6.1f%% %+6.1f%% %+6.1f%% %+6.1f%% %+6.1f%% %6.2f%% "
              "%6.1f %6.1f%% %5.1f%s"
              % (r["name"], r["all13"], r["w0814"], r["w2226"], r["y26"],
                 r["worst"], r["mdd"], r["per_day"], r["part90"], r["brake"],
                 "" if r["ok"] else "  ← 破線"), flush=True)


G = []
for cp in (0.25, 0.35, 0.50):
    G.append(ev("單筆上限 %.0f%%（幅度 50/25）" % (cp * 100),
                brake=((T1, 0.50), (T2, 0.25)), cap_pct=cp))
show(G, "G 階段：單筆上限（最後一個尺寸旋鈕）")

H = []
for s1, s2 in ((0.50, 0.25), (0.52, 0.26), (0.55, 0.28), (0.55, 0.30), (0.58, 0.32)):
    H.append(ev("煞車幅度 %.0f/%.0f" % (s1 * 100, s2 * 100),
                brake=((T1, s1), (T2, s2))))
H.append(ev("幅度 55/28 + 閾值 ×1.2",
            brake=((T1 * 1.2, 0.55), (T2 * 1.2, 0.28))))
show(H, "H 階段：煞車細格（-5.0 的線落在 50/25 與 60/35 之間）")
