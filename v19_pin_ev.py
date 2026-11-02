# -*- coding: utf-8 -*-
r"""Price the thing Weni is actually afraid of, inside the headline numbers.

The book has always settled a trade that ends pinned on a price limit at that
limit price. That is the price nobody traded: the clear order sits in a queue.
v19_overnight.py measured what it costs to carry those to the next open - 32.3
pct of price-limit-bound trades are still pinned at 13:25, and the carry costs
-2.311 pct of notional on average, -3.149 for SHORT.

Two things to read here. First, the penalty is nearly the same size in A and G:
being unable to buy back is not something removing the stop creates, it is a
shared assumption, and both headline numbers have been carrying it silently.
Second, whether G still clears the objective after paying it honestly.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import v13_target as T

CAP = T.CAP0
PIN = 0.00747  # 32.3 pct pinned x -2.311 pct carry = expected cost per closes-at-limit trade
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08, spread=0.00105)
CASES = [("A 現行（SL 4%、煞車 50/25）", dict(nosl=False, brake=((-0.006, .50), (-0.012, .25)))),
         ("G 不設停損、煞車 45/22", dict(nosl=True, brake=((-0.006, .45), (-0.012, .22))))]

def summarize(tag, y):
    yr = y["yearly"]; ks = sorted(yr)
    v = [yr[k] / CAP * 100 for k in ks]
    def avg(a, b):
        s = [x for k, x in zip(ks, v) if a <= k <= b]
        return sum(s) / len(s)
    return dict(tag=tag, all=sum(v) / len(v), old=avg(2014, 2021), recent=avg(2022, 2026),
                mdd=y["mdd"], worstyr=min(v), n=y["n"], n_pin=y["n_pin"],
                total=sum(yr.values()))

print("配置                              13yr   2014-21  2022-26     MDD   最差年   鎖價筆數   總獲利")
rows = []
for tag, kw in CASES:
    for pin in (0.0, PIN):
        y = T.run(**dict(base, **kw, pin_penalty=pin, capture=False))
        r = summarize("%s｜鎖價成本 %s" % (tag, "未計" if pin == 0 else "已計"), y)
        rows.append(dict(r, pin=pin))
        print("%-36s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %7d %8.0f萬"
              % (r["tag"], r["all"], r["old"], r["recent"], r["mdd"], r["worstyr"],
                 r["n_pin"], r["total"] / 1e4), flush=True)

print("\n鎖價成本對目標的影響：")
for i in range(0, len(rows), 2):
    a, b = rows[i], rows[i + 1]
    print("  %s：近五年 %+.1f%% → %+.1f%%（%+.1fpp）｜13 年 %+.1f%% → %+.1f%%｜MDD %.2f%% → %.2f%%｜總獲利 %.0f萬 → %.0f萬"
          % (a["tag"].split("｜")[0], a["recent"], b["recent"], b["recent"] - a["recent"],
             a["all"], b["all"], a["mdd"], b["mdd"], a["total"] / 1e4, b["total"] / 1e4))
pd.DataFrame(rows).to_csv("_pin_cost.csv", index=False)
print("\nsaved _pin_cost.csv")
