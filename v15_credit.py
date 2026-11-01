# -*- coding: utf-8 -*-
"""What this account can actually run, given the broker's line.

Account facts confirmed by Weni on 2026-11-01: the broker granted a line of
4,500,000 and extends NO financing. Past 4,500,000 of placed notional an order is
simply not accepted. So the notional ceiling is min(equity x multiple, line), and
with no financing the multiple is 1.00 - the ceiling is own cash, 4,500,000.

An earlier version of this file treated the line as a loan ("1.90x needs a line of
8.55M, the peak borrowing is only 4.05M, so it fits"). That was wrong in both
directions: 8.55M is a notional, not a line, and a line with no financing is a
cap, not a loan. The 1.90x the research was tuned at is not available here.

Reports the config this account CAN run (1.00x, path B = the entry live actually
uses), the config it would run if the pre-open price turned out to be usable
(1.00x, path A, no spread paid), and what 1.90x would have been for comparison.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as T

CAP0 = T.CAP0
# 2026-11-02: the shipped brake shrinks to 50/25, not 30/12 (v16_search.py).
LIVE = ((-0.006, 0.50), (-0.012, 0.25))
BASE = dict(brake=LIVE, liq=0.10, gap_max=0.04, gap_max_long=0.08)
LINE = 4_500_000

CASES = [
    ("B 1.00x  出貨版（無融資，live 的進場方式）", 1.00, T.SPREAD, LINE),
    ("A 1.00x  競價版（無融資，不付價差）", 1.00, 0.0, LINE),
    ("B 1.90x  需要 855 萬額度（本帳戶沒有）", 1.90, T.SPREAD, 8_550_000),
]

print("=" * 100)
print("帳戶：自有 %d 萬｜券商額度 %d 萬｜無融資 → 名義上限 %d 萬"
      % (CAP0 / 10000, LINE / 10000, LINE / 10000))
print("名義上限 = min(淨值 x 倍數, 額度)。無融資所以倍數 1.00，兩個上限在 450 萬相等，"
      "不需要借款。")
print("=" * 100)
print("  %-38s %9s %9s %9s %8s %7s %7s %6s"
      % ("設定", "13yr", "2025", "2026", "最差年", "部位MDD", "峰值名義", "筆/日"))
out = {}
for name, ex, sp, line in CASES:
    r = T.run(**dict(BASE, exposure=ex, spread=sp))
    y = r["yearly"]; yrs = sorted(y)
    rets = [y[k] / CAP0 * 100 for k in yrs]
    peak = r["expo_max"] / 100.0 * CAP0
    print("  %-38s %+8.1f%% %+8.1f%% %+8.1f%% %+7.1f%% %7.2f%% %6.0f萬 %6.1f"
          % (name, np.mean(rets), y[2025] / CAP0 * 100, y[2026] / CAP0 * 100,
             min(rets), r["mdd"], peak / 10000, r["per_day"]))
    print("      %s 需借款 %s" % ("額度內" if peak <= line else "超出額度，跑不了",
                                  "0（無融資）" if ex <= 1.0 else
                                  "%.0f 萬" % (max(0.0, peak - CAP0) / 10000)))
    out[name] = (r, y, yrs, rets)

r, y, yrs, rets = out[CASES[0][0]]
print()
print("-" * 100)
print("出貨版（B 1.00x）逐年，每一年都釘回 450 萬、獲利出金：")
print("  %-6s %-8s %-8s %10s %10s" % ("年", "報酬%", "對450萬", "筆數", "勝率"))
mon = r["monthly"]
assert abs(y[2026] / CAP0 * 100 - 88.2) < 0.15, (
    "this table must be the 1.00x book, not the last case in CASES: 2026 = %.1f%%"
    % (y[2026] / CAP0 * 100))
tot = 0.0
for k in yrs:
    n = sum(v[1] for m, v in mon.items() if m[0] == k)
    w = sum(v[2] for m, v in mon.items() if m[0] == k)
    tot += y[k]
    print("  %-6d %+7.1f %8.0f萬 %9d %9.1f%%"
          % (k, y[k] / CAP0 * 100, y[k] / 10000, n, w / n * 100 if n else 0.0))
for lo, hi in ((2014, 2021), (2022, 2026)):
    seg = [y[k] / CAP0 * 100 for k in yrs if lo <= k <= hi]
    print("  %d-%d 年均 %+.1f%%（%d 年）" % (lo, hi, sum(seg) / len(seg), len(seg)))
print("  13 年總獲利 %.0f 萬（不是可複利的 CAGR：每年本金都釘回 450 萬）" % (tot / 10000))

print()
print("-" * 100)
print("額度是絕對金額，不會跟著淨值複利。若改成不出金、讓淨值成長：")
for eq in (4_500_000, 5_000_000, 6_000_000, 10_000_000, 20_000_000):
    ceil = min(eq * 1.00, LINE)
    print("  淨值 %6.0f 萬 -> 名義上限 %6.0f 萬（等效 %.2fx）%s"
          % (eq / 10000, ceil / 10000, ceil / eq,
             "" if ceil >= eq else "← 額度綁住，部位被券商額度壓著，不是策略縮的"))
print("  所以這個策略的胃納量就是 450 萬。要更大的資金，要的是額度，不是更好的參數。")
