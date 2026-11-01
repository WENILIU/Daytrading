# -*- coding: utf-8 -*-
r"""The configuration that reaches the objective, and what it costs per trade.

Chosen on 2014-2021 only (v18_brake2.py): no per-trade stop, equity brake
-0.6% -> 45% / -1.2% -> 22%. Everything else is the shipped book unchanged:
exposure 1.00x against the broker's absolute 4.5M line with no financing, entry
at 09:00+60s priced from the five-level book and paying the half-spread, TP 12%,
13:25 force close, 處置排除 + 借券確認 + 流動性 + 整張 + 5% participation cap,
30 orders/day cap, costs at 0.111% a side.

The point of capture=True is that the risk questions get answered from the same
book the headline numbers come from. A per-trade stop is not free and it is not
free to remove: what you buy with it, and what you give up, are both in here.
"""
import warnings; warnings.filterwarnings("ignore")
import collections
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
brake_new = ((-0.006, 0.45), (-0.012, 0.22))
brake_old = ((-0.006, 0.50), (-0.012, 0.25))
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08, spread=0.00105,
            capture=True)
CASES = [("現行 A（SL 4%、煞車 50/25）", dict(nozt=False, nosl=False, brake=brake_old)),
         ("新 G（不設停損、煞車 45/22）", dict(nozt=False, nosl=True, brake=brake_new))]
res = {}
for tag, kw in CASES:
    res[tag] = T.run(**dict(base, **kw))
    print("done:", tag, flush=True)


def yearly_book(trades):
    """Per-year return, drawdown and trade stats on a book pinned at 4.5M."""
    by_day = collections.defaultdict(float)
    by_day_n = collections.defaultdict(int)
    for d, code, dr, notional, gross, reason, entry, ex in trades:
        by_day[d] += notional * gross
        by_day_n[d] += 1
    out = {}
    for d, y in by_day.items():
        out.setdefault(d[:4], []).append((d, y, by_day_n[d]))
    return out


for tag, y in res.items():
    print("\n" + "=" * 92)
    print(tag)
    print("=" * 92)
    yr = y["yearly"]; ks = sorted(yr)
    v = [yr[k] / CAP * 100 for k in ks]
    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    tr = pd.DataFrame([dict(zip("date code dir notional gross reason entry exit".split(), t))
                      for t in y["trades"]])
    tr["pnl"] = tr["notional"] * tr["gross"]
    bd = yearly_book(y["trades"])
    print("年      報酬%    對450萬      筆數   勝率%   平均每筆   年內回撤   虧損筆占比")
    for k in ks:
        rows = sorted(bd[str(k)])
        book = CAP; peak = CAP; mdd = 0.0
        for _, pnl, _n in rows:
            book = min(CAP, book + pnl); peak = max(peak, book)
            mdd = min(mdd, (book - peak) / peak * 100)
        g = tr[tr["date"].str[:4] == str(k)]
        print("%d  %+7.1f  %+7.0f萬  %6d  %5.1f  %+7.3f%%  %+7.2f%%  %6.1f%%"
              % (k, yr[k] / CAP * 100, yr[k] / 1e4, len(g),
                 (g["gross"] > 0).mean() * 100, g["gross"].mean() * 100, mdd,
                 (g["gross"] < 0).mean() * 100))
    print("-" * 92)
    print("13 年年均 %+.1f%%｜2014-2021 %+.1f%%｜2022-2026 %+.1f%%｜部位 MDD %.2f%%｜最差年 %+.1f%%｜筆/日 %.1f"
          % (sum(v) / len(v), avg(2014, 2021), avg(2022, 2026), y["mdd"], min(v), y["per_day"]))
    print("13 年總獲利 %.0f 萬｜勝率 %.1f%%｜平均每筆 %+.3f%%"
          % (sum(yr.values()) / 1e4, (tr["gross"] > 0).mean() * 100, tr["gross"].mean() * 100))
    print("\n逐筆風險（這才是拿掉停損真正改變的東西）：")
    q = tr["gross"] * 100
    print("   最差單筆 %+.2f%%（%.0f 元）｜p1 %+.2f%%｜p5 %+.2f%%｜p25 %+.2f%%｜中位 %+.2f%%"
          % (q.min(), tr.loc[q.idxmin(), "pnl"], q.quantile(.01), q.quantile(.05),
             q.quantile(.25), q.median()))
    print("   虧損超過 4%%（舊停損會擋掉的）：%d 筆（%.1f%%），合計 %.0f 萬"
          % ((q < -4).sum(), (q < -4).mean() * 100, tr.loc[q < -4, "pnl"].sum() / 1e4))
    print("   虧損超過 6%%：%d 筆（%.1f%%），合計 %.0f 萬"
          % ((q < -6).sum(), (q < -6).mean() * 100, tr.loc[q < -6, "pnl"].sum() / 1e4))
    day = tr.groupby("date")["pnl"].sum()
    print("   最差單日 %.0f 元（%.2f%%）｜最好單日 %.0f 元" % (day.min(), day.min() / CAP * 100, day.max()))
    print("   出場原因：", dict(collections.Counter(tr["reason"]).most_common()))
