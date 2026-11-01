# -*- coding: utf-8 -*-
"""Stage D: combine what stage A and C found, under the -5 pct MDD gate.

Stage A (brake): softening the SHRINK FACTORS from 30/12 to 50/25 buys +5 pct on
2022-2026 and keeps MDD at -4.60 - risk control still fires, it just does not
starve the book to 12 pct. Raising the THRESHOLDS instead buys more but breaks
the line. Brake fully off: MDD -14 pct, so the brake is doing real work.
Stage B (order size): +0.3 pct once the marginal participation cost is charged.
The per-order cap is not the binding constraint; the 450 萬 total is.
Stage C (gap caps): 6/10 buys +2.8 pct at MDD -4.87.

Both A and C spend MDD budget, so the combinations have to be measured, not added.
The spread=0 rows are the opening-auction path: +9 pct if the pre-open indicative
price turns out to update (measured today, 2026-11-02). They are conditional and
labelled as such.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
SHIP = dict(brake=((-0.006, 0.30), (-0.012, 0.12)), liq=0.10, gap_max=0.04,
            gap_max_long=0.08, exposure=1.00, spread=T.SPREAD)
MDD_FLOOR = -5.0
T1, T2 = -0.006, -0.012


def ev(name, **over):
    cfg = dict(SHIP); cfg.update(over)
    r = T.run(**cfg)
    y = r["yearly"]; yrs = sorted(y)
    def win(lo, hi):
        s = [y[k] / CAP0 * 100 for k in yrs if lo <= k <= hi]
        return sum(s) / len(s) if s else float("nan")
    rets = [y[k] / CAP0 * 100 for k in yrs]
    return dict(name=name, all13=np.mean(rets), w0814=win(2014, 2021),
                w2226=win(2022, 2026), y25=y[2025] / CAP0 * 100,
                y26=y[2026] / CAP0 * 100, mdd=r["mdd"], worst=min(rets),
                per_day=r["per_day"], part90=r["part90"], brake=r["brake_pct"],
                ok=r["mdd"] >= MDD_FLOOR)


def show(rows, title):
    print("\n" + "=" * 118); print(title); print("=" * 118)
    print("  %-44s %7s %7s %7s %7s %7s %7s %7s %6s %6s %5s"
          % ("設定", "13yr", "14-21", "22-26", "2025", "2026", "最差年",
             "MDD", "筆/日", "part90", "煞車%"))
    for r in sorted(rows, key=lambda x: -x["w2226"]):
        print("  %-44s %+6.1f%% %+6.1f%% %+6.1f%% %+6.1f%% %+6.1f%% %+6.1f%% "
              "%6.2f%% %6.1f %6.1f%% %5.1f%s"
              % (r["name"], r["all13"], r["w0814"], r["w2226"], r["y25"], r["y26"],
                 r["worst"], r["mdd"], r["per_day"], r["part90"], r["brake"],
                 "" if r["ok"] else "  ← MDD 破線"), flush=True)


D = [ev("基準（出貨版）")]
D.append(ev("幅度 50/25", brake=((T1, 0.50), (T2, 0.25))))
D.append(ev("幅度 60/35", brake=((T1, 0.60), (T2, 0.35))))
D.append(ev("幅度 50/25 + 閾值 ×1.5",
            brake=((T1 * 1.5, 0.50), (T2 * 1.5, 0.25))))
D.append(ev("幅度 50/25 + gap 6/10",
            brake=((T1, 0.50), (T2, 0.25)), gap_max=0.06, gap_max_long=0.10))
D.append(ev("幅度 50/25 + gap 5/10",
            brake=((T1, 0.50), (T2, 0.25)), gap_max=0.05, gap_max_long=0.10))
D.append(ev("幅度 40/20 + gap 6/10",
            brake=((T1, 0.40), (T2, 0.20)), gap_max=0.06, gap_max_long=0.10))
D.append(ev("幅度 50/25 + gap 6/10 + liq 20%",
            brake=((T1, 0.50), (T2, 0.25)), gap_max=0.06, gap_max_long=0.10,
            liq=0.20, part_delta=True))
show(D, "D 階段：組合（名義 450 萬、吃半價差 = 現在就能做的）")

E = [ev("D 最佳 + 競價不付價差（有條件）",
        brake=((T1, 0.50), (T2, 0.25)), gap_max=0.06, gap_max_long=0.10,
        spread=0.0),
     ev("幅度 50/25 + 競價（有條件）",
        brake=((T1, 0.50), (T2, 0.25)), spread=0.0),
     ev("現行 + 競價（有條件）", spread=0.0)]
show(E, "E 階段：若 11/02 量到盤前指示價會更新（不付價差），同一組參數的數字")

F = [ev("nozt：觸漲跌停不停損，改結在收盤（診斷用）", nozt=True),
     ev("nozt + 幅度 50/25（診斷用）", nozt=True,
        brake=((T1, 0.50), (T2, 0.25)))]
show(F, "F 階段：診斷 - 被漲跌停 cap 住的停損值多少")
