"""Entry slippage, measured from the 1-minute corpus, on the orders the strategy
actually places.

The backtest fills at the 09:00:00 opening print. That price is not obtainable:
RISK1 measured the opening print becoming VISIBLE at p50 9-10s after 09:00:00, and
by then the tape has moved. Gap-fade is the worst possible strategy for this,
because the whole edge is that the opening print is an outlier:

  SHORT (sold at the open, name gapped UP) - if the fade is real the price is
    already lower when we can act, so we sell lower. Cost.
  LONG  (bought at the open, name gapped DOWN) - if the bounce is real the price
    is already higher. Cost.

Both directions pay. That is what this measures, so the target CAGR can be quoted
net of it instead of assuming a fill nobody gets.

Fill proxies. Minute bars cannot resolve 10s, so two brackets:
  f60  = close of the 09:00 bar  - the price ~60s after the open. Conservative.
  f120 = close of the 09:01 bar  - ~120s. Worse case.
The true 10-25s fill sits between the open print and f60, closer to the open.
Reporting f60 as the cost is therefore an over-estimate of the penalty, which is
the direction you want when the number decides whether a strategy goes live.

Sanity check first: the 09:00 bar open must equal the backtest entry price, or the
backtest and this corpus are not describing the same print.

Usage: python v13_slippage.py
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from v13_engine import run_backtest, CAP0
import v13_sizing as S
from min_bars import bars_for

ORDER_CAP = 30
CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
_, got, _ = run_backtest(capture=("2023-01-01", "2026-12-31"), capital=CAP0, **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)

rule = {k: v for k, v in S.R9.items() if k != "min_turnover_factor"}
rule["min_turnover_factor"] = 0.5

rows = []; miss = 0; mismatch = 0; n_orders = 0
for d, g in D.groupby("date"):
    g = g.sort_values("_rank"); rem = CAP0; n_day = 0
    day = str(pd.Timestamp(d).date())
    for _, r in g.iterrows():
        if n_day >= ORDER_CAP:
            break
        pr = float(r["entry"]); code = str(r["stock"])
        dv1 = float(TO1.at[d, code]) if (code in TO1.columns and d in TO1.index) else np.nan
        n = S.lots_for(rule, float(r["_weight"]), pr, rem, dv1, capital=CAP0)
        if n <= 0:
            continue
        rem -= n * 1000.0 * pr; n_day += 1; n_orders += 1
        bs = bars_for(code, day)
        if not bs:
            miss += 1
            continue
        b0 = [b for b in bs if b[0][11:16] == "09:00"]
        b1 = [b for b in bs if b[0][11:16] == "09:01"]
        if not b0:
            miss += 1
            continue
        # need the raw OHLC, not the dollar tuple -> re-read that one bar
        rows.append((day, code, str(r["direction"]), pr, n * 1000.0 * pr))

print("策略在 2023+ 實際會下的單：%d 筆，其中 %d 筆有 1 分 K（%.1f%%）" %
      (n_orders, len(rows), len(rows) / n_orders * 100))
pd.DataFrame(rows, columns=["date", "code", "dir", "entry_bt", "notional"]).to_csv(
    r"D:\AI專案\StockAgent\DayTrading\slip_orders.csv", index=False, encoding="utf-8-sig")
print("written D:\\AI專案\\StockAgent\\DayTrading\\slip_orders.csv")
