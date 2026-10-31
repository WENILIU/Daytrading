"""The two exit-side assumptions the backtest also makes, measured.

1. Force close. The backtest exits at day_close, i.e. the 13:30 print. Live exits
   at 13:25. Five minutes of drift on a position opened as a gap-fade. Measured by
   comparing the close of the 13:25 bar with the day close.

2. Stop-loss fill. The backtest fills the stop exactly at the stop price. Live uses
   a price-triggered order that becomes a market order once touched, so the fill is
   somewhere at or beyond the level. Minute bars cannot resolve the tick, so the
   bound used here is the close of the bar that first breaches the level - "we
   reacted at the end of that minute". Real slippage is between 0 and that.

Take-profit is NOT measured as a cost: TP orders are limits, so a fill at the
target price or better is the correct assumption, not an optimistic one.

Usage: python v13_exitcost.py
"""
import os, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from v13_engine import run_backtest, CAP0, exit_of_legal
import v13_sizing as S
from min_bars import bars_for

ORDER_CAP = 30
CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
_, got, _ = run_backtest(capture=("2023-01-01", "2026-12-31"), capital=CAP0, **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
rule = {k: v for k, v in S.R9.items() if k != "min_turnover_factor"}
rule["min_turnover_factor"] = 0.5

fc = []; sl = []; n_fc = 0; n_sl = 0; miss = 0
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
        rem -= n * 1000.0 * pr; n_day += 1
        ex, slp, tpp, reason, gross = exit_of_legal(
            r["direction"], pr, float(r["day_high"]), float(r["day_low"]), float(r["day_close"]),
            float(r["lu"]), float(r["ld"]), float(r["tick"]), float(r["tp"]))
        bs = bars_for(code, day)
        if not bs:
            miss += 1
            continue
        px = {}
        for b in bs:
            px[b[0][11:16]] = b
        if reason == "13:25 強制平倉":
            n_fc += 1
            # the corpus has no 13:25 bar - it jumps 13:24 -> 13:30. Bars are
            # START-labelled (09:00 open == the exchange opening print, matched the
            # backtest entry on 1718/1718 orders), so the 13:24 bar close is the
            # price at ~13:24:59, which is the 13:25 exit we would actually get.
            b25 = px.get("13:24")
            if b25 is None:
                continue
            p25 = b25[3]
            cl = float(r["day_close"])
            sgn = -1.0 if r["direction"] == "SHORT" else 1.0
            # positive = closing at 13:25 is WORSE than the backtest's 13:30 print
            fc.append(sgn * (cl - p25) / pr)
        elif reason.startswith("停損"):
            n_sl += 1
            lvl = slp
            sgn = -1.0 if r["direction"] == "SHORT" else 1.0
            hit = None
            for t in sorted(px):
                if t < "09:00" or t > "13:24":
                    continue
                b = px[t]
                breached = (b[5] <= lvl) if r["direction"] == "LONG" else (b[4] >= lvl)
                if breached:
                    hit = b
                    break
            if hit is None:
                continue
            fill = hit[3]                     # bar close of the breaching minute
            if r["direction"] == "LONG":
                fill = min(lvl, max(hit[5], fill))
            else:
                fill = max(lvl, min(hit[4], fill))
            # positive = worse than filling exactly at the stop level
            sl.append(sgn * (fill - lvl) / pr)

print("結算樣本：強制平倉 %d 筆（可算 %d）、停損 %d 筆（可算 %d）、無分K %d" % (n_fc, len(fc), n_sl, len(sl), miss))
print()
print("1) 13:25 平倉 vs 回測的 13:30（正值 = 13:25 平掉比較差）")
a = np.array(fc) * 100
print("   n=%d  平均 %+.4f%%  p50 %+.4f%%  p10 %+.3f%%  p90 %+.3f%%  變差的比例 %.1f%%" %
      (len(a), a.mean(), np.percentile(a, 50), np.percentile(a, 10), np.percentile(a, 90), (a > 0).mean() * 100))
print("   換算成每筆成本：%+.4f%%（這是入場滑價同量級還是可忽略，看這個數）" % a.mean())
print()
print("2) 停損觸價單 vs 停損價（正值 = 成交比停損價更差；上界口徑）")
b = np.array(sl) * 100
print("   n=%d  平均 %+.4f%%  p50 %+.4f%%  p90 %+.3f%%  max %+.3f%%" %
      (len(b), b.mean(), np.percentile(b, 50), np.percentile(b, 90), b.max()))
