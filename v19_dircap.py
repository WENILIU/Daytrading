# -*- coding: utf-8 -*-
r"""Cap one direction per day - the only lever aimed at the drawdown this strategy has.

The book is below 95 pct of the line on exactly one of 2,521 days: 2021-05-18,
29 of 30 trades SHORT, 99 pct exposure, -5.00 pct in a session. Nothing that
reacts after the fact can touch that, because the book was at its peak that
morning. A per-day cap on one direction is a pre-trade rule: it costs nothing on
the days that are balanced, and it is exactly the days that are one-sided that
produce the loss.

Two things to watch, not just the headline:
  - does MDD actually move off -5.00 pct, and onto what date (if it does not, the
    cap did not do what it claims);
  - how many signals the cap blocks - a cap that quietly deletes a fifth of the
    book is not free, it is exposure reduction wearing a better name.
Choose on 2014-2021, report 2022-2026.
"""
import warnings; warnings.filterwarnings("ignore")
import collections
import pandas as pd
import v13_target as T

CAP = T.CAP0
PIN = 0.00747
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08, spread=0.00105,
            pin_penalty=PIN)
BRAKE = {"A 50/25": ((-0.006, .50), (-0.012, .25)),
         "G 45/22": ((-0.006, .45), (-0.012, .22))}
CAPS = [None, 0.70, 0.60, 0.50, 0.40]

def book_days(trades):
    by = collections.defaultdict(float)
    for d, *_rest in trades:
        by[d] += trades_to_pnl(_rest) if False else 0
    return by

def trades_to_pnl(rest):
    notional, gross = rest[2], rest[3]
    return notional * gross

print("配置            dir_cap   13yr   2014-21  2022-26     MDD   最差年   筆/日  被擋訊號")
rows = []
for bname, brake in BRAKE.items():
    nosl = bname.startswith("G")
    for dc in CAPS:
        y = T.run(**dict(base, nosl=nosl, brake=brake, dir_cap=dc, capture=(dc in (None, 0.5))))
        yr = y["yearly"]; ks = sorted(yr)
        v = [yr[k] / CAP * 100 for k in ks]

        def avg(a, b):
            s = [x for k, x in zip(ks, v) if a <= k <= b]
            return sum(s) / len(s)
        lab = "無上限" if dc is None else "%.0f%%" % (dc * 100)
        flag = "  <== 達標" if (y["mdd"] >= -5.0 and avg(2022, 2026) >= 100.0) else ""
        print("%-14s %-8s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %5.1f %7d%s"
              % (bname, lab, sum(v) / len(v), avg(2014, 2021), avg(2022, 2026), y["mdd"],
                 min(v), y["per_day"], y["n_dircap"], flag), flush=True)
        rows.append(dict(cfg=bname, dir_cap=lab, all=sum(v) / len(v), old=avg(2014, 2021),
                         recent=avg(2022, 2026), mdd=y["mdd"], worst_year=min(v),
                         per_day=y["per_day"], blocked=y["n_dircap"]))
        if dc == 0.5 and nosl:
            tr = pd.DataFrame([dict(zip("date code dir notional gross reason entry exit".split(), t))
                               for t in y["trades"]])
            tr["pnl"] = tr["notional"] * tr["gross"]
            day = tr.groupby("date")["pnl"].sum().sort_values()
            print("      worst 3 days now:", [(k, round(x)) for k, x in day.head(3).items()])
pd.DataFrame(rows).to_csv("_dir_cap.csv", index=False)
print("\nsaved _dir_cap.csv")
