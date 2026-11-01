# -*- coding: utf-8 -*-
r"""What is the worst single trade under no-stop, and is it a real price?

A day trade that opens on a gap and is closed at 13:25 cannot lose more than the
distance from its entry to the price limit - about 5.8 pct for a short at the
4 pct gap cap, about 2 pct for a long at the 8 pct cap. A -13 pct reading means
one of those inputs is not what it looks like: the gap filter is on the MARKET
ADJUSTED gap, so the raw gap can be much larger, and the reference price for the
limit can be moved by 除權息. Both are real, and both change what the number
means for a live order. This prints the trades so the bound can be checked
against the panel instead of argued about.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import v13_target as T

y = T.run(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
          order_cap=30, cost_mode="measured", gap_max_long=0.08, spread=0.00105,
          nosl=True, brake=((-0.006, .45), (-0.012, .22)), capture=True)
tr = pd.DataFrame([dict(zip("date code dir notional gross reason entry exit".split(), t))
                   for t in y["trades"]])
tr["pnl"] = tr["notional"] * tr["gross"]
key = list(zip([pd.Timestamp(x) for x in tr["date"]], tr["code"]))
sub = T.D.set_index([T.D["date"], T.D["stock"]])
cols = []
for k in key:
    try:
        r = sub.loc[k]
    except KeyError:
        cols.append((None,) * 6); continue
    if isinstance(r, pd.DataFrame):
        r = r.iloc[0]
    cols.append((float(r["lu"]), float(r["ld"]), float(r["prev_close"]),
                 float(r["raw_gap"]), float(r["adj_gap"]), float(r["day_close"])))
tr[["lu", "ld", "prev", "raw_gap", "adj_gap", "dcl"]] = pd.DataFrame(cols, index=tr.index)
tr["worst_possible"] = (tr["exit"] - tr["entry"]) / tr["entry"] * 100
worst = tr.nsmallest(12, "gross")
print("日期        股票   方向  進場      出場      漲停     跌停     前收      raw_gap  adj_gap  損益%   到價限的理論上限%")
for _, r in worst.iterrows():
    print("%s %-6s %-5s %8.2f %8.2f %8.2f %8.2f %8.2f  %+6.1f%% %+6.1f%%  %+6.2f%%  %+7.2f%%"
          % (r["date"], r["code"], r["dir"], r["entry"], r["exit"], r["lu"], r["ld"],
             r["prev"], r["raw_gap"] * 100, r["adj_gap"] * 100, r["gross"] * 100,
             r["worst_possible"]))
print("\n出場價是否都在當日漲跌停之內：",
      bool(((tr["exit"] <= tr["lu"] + 1e-9) & (tr["exit"] >= tr["ld"] - 1e-9)).all()))
print("出場價等於收盤價的比例：%.1f%%" % ((abs(tr["exit"] - tr["dcl"]) < 1e-9).mean() * 100))
print("\n按方向的理論最大虧損（到價限，未含成本）：")
for d, g in tr.groupby("dir"):
    print("   %-5s n=%5d  最差 %+.2f%%   理論上限 %+.2f%%"
          % (d, len(g), g["gross"].min() * 100, g["worst_possible"].min()))
