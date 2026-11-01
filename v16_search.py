# -*- coding: utf-8 -*-
"""Can the book reach 100 pct a year inside a 4,500,000 notional cap?

The account has no financing, so the notional ceiling is own cash: exposure is
pinned at 1.00 and every candidate here runs at 1.00. That removes the one lever
the previous search used to buy return (1.90x), so the question becomes: with the
same 450 萬 of placed notional, can the SAME money be pointed at better trades?

Two levers can move return without touching order size, and one cannot:
  brake      - when to shrink. Does not change order size, so ENTRY_COST (measured
               on this exact book) applies unchanged. The shipped brake fires on
               47.6 pct of days, which is a large amount of starved capital.
  gap caps   - which signals to take. Also size-neutral.
  liq        - how big each order may be. This DOES change size, so it is only
               comparable with part_delta=True: the marginal participation cost
               above the shipped 10 pct cap, using the measured cost-vs-participation
               curve. Without it, raising liq looks free and is not.

Reported per window on purpose. The user asked for the recent five years; a
configuration chosen on 2022-2026 is in-sample there, so 2014-2021 is shown next
to it as the part that was never used to pick anything.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
SHIP = dict(brake=((-0.006, 0.30), (-0.012, 0.12)), liq=0.10, gap_max=0.04,
            gap_max_long=0.08, exposure=1.00, spread=T.SPREAD)
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
                w2226=win(2022, 2026), y25=y[2025] / CAP0 * 100,
                y26=y[2026] / CAP0 * 100, mdd=r["mdd"], worst=min(rets),
                per_day=r["per_day"], part90=r["part90"],
                brake=r["brake_pct"], ok=r["mdd"] >= MDD_FLOOR)


def show(rows, title):
    print("\n" + "=" * 118)
    print(title)
    print("=" * 118)
    print("  %-40s %7s %7s %7s %7s %7s %7s %7s %6s %6s %5s"
          % ("設定", "13yr", "14-21", "22-26", "2025", "2026", "最差年",
             "MDD", "筆/日", "part90", "煞車%"))
    for r in sorted(rows, key=lambda x: -x["w2226"]):
        print("  %-40s %+6.1f%% %+6.1f%% %+6.1f%% %+6.1f%% %+6.1f%% %+6.1f%% "
              "%6.2f%% %6.1f %6.1f%% %5.1f%s"
              % (r["name"], r["all13"], r["w0814"], r["w2226"], r["y25"], r["y26"],
                 r["worst"], r["mdd"], r["per_day"], r["part90"], r["brake"],
                 "" if r["ok"] else "  ← MDD 破線"))
    print("  （MDD 門檻 %.1f%%；破線的列不入選）" % MDD_FLOOR, flush=True)


BASE_T = (-0.006, -0.012)
A = [ev("現行出貨版（基準）")]
for k in (1.5, 2.0, 3.0, 5.0, 10.0):
    A.append(ev("煞車閾值 ×%.1f" % k,
                brake=((BASE_T[0] * k, 0.30), (BASE_T[1] * k, 0.12))))
A.append(ev("煞車完全關閉", brake=None))
for s1, s2 in ((0.5, 0.25), (0.7, 0.40), (0.85, 0.60)):
    A.append(ev("煞車縮倉幅度 %.0f%%/%.0f%%" % (s1 * 100, s2 * 100),
                brake=((BASE_T[0], s1), (BASE_T[1], s2))))
A.append(ev("閾值 ×2 + 幅度 50%/25%",
            brake=((BASE_T[0] * 2, 0.50), (BASE_T[1] * 2, 0.25))))
show(A, "A 階段：煞車（不改變單量，進場成本模型完全適用）")

B = [ev("liq 10%（現行）")]
for l in (0.15, 0.20, 0.30, 0.50):
    B.append(ev("liq %.0f%% + 邊際參與率成本" % (l * 100), liq=l, part_delta=True))
    B.append(ev("liq %.0f%%（不計邊際成本，高估）" % (l * 100), liq=l))
show(B, "B 階段：單量上限（會改變單量；只有附邊際成本那幾列可比）")

C = [ev("gap 4%/8%（現行）")]
for gs, gl in ((0.05, 0.10), (0.06, 0.10), (0.03, 0.08), (0.04, 0.12)):
    C.append(ev("gap %.0f%%/%.0f%%" % (gs * 100, gl * 100), gap_max=gs, gap_max_long=gl))
show(C, "C 階段：gap 上限（size-neutral）")
