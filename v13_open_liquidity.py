"""What share of the day had already traded when the strategy places its order?

The participation gate is judged against T-1 dollar turnover, and I reported
participation against FULL-DAY turnover. Both understate the real impact, because
the strategy trades in the first seconds after the open, when only a fraction of
the day's volume exists to trade against.

Resolution note, stated up front: the local corpus is minute bars, so 10s and 30s
cannot be measured. The 09:01 bar is the closest proxy for the moment we trade -
the opening auction prints at 09:00:00 and its volume lands in that bar. But that
bar also contains the ~50 seconds of continuous trading AFTER our order goes out,
so it overstates the liquidity available to us: every participation number below is
a LOWER bound on real impact. Later offsets show how fast the rest of the day
arrives. Units and the filename-vs-content trap are handled in min_bars.py.

Windows: daily files cover 2025-03-26..2025-10-27, month files 2023-05, 2024-01,
2025-01, 2026-01. Only orders inside those windows are measured; the rest of the
history is not, and the sample is stated with every table.

Usage: python v13_open_liquidity.py
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from v13_engine import run_backtest, CAP0, COST, exit_of_legal
import v13_sizing as S
from min_bars import curve, OFFSETS

CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
_, got, _ = run_backtest(capture=("2023-01-01", "2026-12-31"), capital=CAP0, **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
ORDER_CAP = 30

for fname, factor in (("factor 5.0（現行）", 5.0), ("factor 2.0", 2.0),
                      ("無門檻（全部訊號，反推用）", None)):
    rule = {**S.R9, "min_turnover_factor": factor}
    if factor is None:
        rule.pop("min_turnover_factor")
    recs = []
    for d, g in D.groupby("date"):
        day = str(pd.Timestamp(d).date())
        g = g.sort_values("_rank"); rem = CAP0; n_day = 0
        for _, r in g.iterrows():
            if n_day >= ORDER_CAP:
                break
            pr = float(r["entry"]); code = str(r["stock"])
            dv1 = float(TO1.at[d, code]) if (code in TO1.columns and d in TO1.index) else np.nan
            n = S.lots_for(rule, float(r["_weight"]), pr, rem, dv1, capital=CAP0)
            if n <= 0:
                continue
            rem -= n * 1000.0 * pr; n_day += 1
            recs.append((day, code, n * 1000.0 * pr, float(r["_weight"]), dv1))
    hit = 0; miss = 0; no_open = 0
    rows = []
    for day, code, notional, wgt, dv1 in recs:
        c = curve(code, day)
        if c is None:
            miss += 1
            continue
        cur, dayval = c
        hit += 1
        if cur["09:00"] <= 0 and cur["09:01"] <= 0:
            no_open += 1
        rows.append((day, code, notional, wgt, dv1, dayval, *[cur[o] for o in OFFSETS]))
    R = pd.DataFrame(rows, columns=["date", "code", "notional", "weight", "dv1", "day_value"] + OFFSETS)
    print("=== %s ===" % fname)
    print("策略實際下的單：%d 筆落在有 1 分 K 的區間，%d 筆沒有資料（可用率 %.1f%%）" %
          (hit, miss, hit / (hit + miss) * 100))
    if not hit:
        continue
    R.to_csv(r"D:\AI專案\StockAgent\DayTrading\open_liquidity_%s.csv" % ("off" if factor is None else str(factor).replace(".", "_")),
             index=False, encoding="utf-8-sig")
    print()
    print("開盤後已成交占全天比例的分布（這些都是開盤跳空的股票，比大盤集中得多）")
    print("  時點      p10     p25     p50     p75     p90     加權p50")
    for o in OFFSETS:
        ws = np.average(R[o], weights=R["notional"])
        print("  %-8s %6.2f%% %6.2f%% %6.2f%% %6.2f%% %6.2f%% %8.2f%%" %
              (o, np.percentile(R[o], 10)*100, np.percentile(R[o], 25)*100, np.percentile(R[o], 50)*100,
               np.percentile(R[o], 75)*100, np.percentile(R[o], 90)*100, ws*100))
    print()
    print("09:00 與 09:01 都沒有成交的股票：%d / %d 筆（%.1f%%）" % (no_open, hit, no_open / hit * 100))
    print("  這些股票 09:01 那根沒有 bar，開盤沒有流動性，任何單都會自己把價格推出去。")
    print("  下面的參與率分布把它們排除（分母為 0 無法定義），單獨列出口徑。")
    ok = R[R["09:00"] > 0].copy()
    ok["part_full"] = ok["notional"] / ok["day_value"]
    ok["part_0900"] = ok["notional"] / (ok["day_value"] * ok["09:00"])
    ok["part_open"] = ok["notional"] / (ok["day_value"] * ok["09:01"])
    ok["part_5min"] = ok["notional"] / (ok["day_value"] * ok["09:05"])
    print()
    print("我實際佔掉的比例（notional / 該時點已累计成交額）")
    print("  09:00 那根不是單筆競價（2330 2025-09-01 高1155/低1145），它混了競價與頭一分鐘，")
    print("  所以它是可用流動性的下界、也就是參與率的上界。我們的單在開盤後 ~10 秒送出，")
    print("  真實數字落在 09:00 與 09:01 兩行之間，而且比較靠近 09:00 那一行。")
    for col, lbl in (("part_full", "佔全天成交額"), ("part_5min", "佔前5分鐘"), ("part_open", "佔09:01累計"), ("part_0900", "佔09:00那根")):
        q = ok[col] * 100
        print("  %-14s p50 %7.3f%%  p90 %7.2f%%  p99 %7.2f%%  max %8.1f%%" %
              (lbl, np.percentile(q, 50), np.percentile(q, 90), np.percentile(q, 99), q.max()))
    print()
    rr = (ok["day_value"] / ok["dv1"]).dropna()
    print("当天成交額 / T-1 成交額（門檻寫在 T-1 上，錢花在当天，這個倍數決定門檻有多保守）")
    print("  p10 %.2fx  p50 %.2fx  p75 %.2fx  p90 %.2fx" %
          (np.percentile(rr, 10), np.percentile(rr, 50), np.percentile(rr, 75), np.percentile(rr, 90)))
    print()
    print("反推 min_turnover_factor（不是選的，是算出來的）")
    print("  門檻是 dv1 >= factor*capital，所以 part_open <= notional/(factor*capital*share_09:01)")
    print("  要讓 part_open <= X，逐筆需要 factor = notional/(X*capital*share_09:01)")
    print("  下表是逐筆 factor 需求的分位數：設成該值就只有那一成訂單會被自己擋掉")
    print("    上限X      樂觀(分母09:01) p50    p75    p90    p95    p99     保守(分母09:00) p50    p75    p90    p95    p99")
    for X in (0.02, 0.05, 0.10, 0.20, 0.30):
        fa = ok["notional"] / (X * CAP0 * ok["09:01"])
        fb = ok["notional"] / (X * CAP0 * ok["09:00"])
        print("    %3.0f%%  樂觀 %6.1f %6.1f %6.1f %6.1f %6.1f   保守 %6.1f %6.1f %6.1f %6.1f %6.1f" %
              (X * 100,
               np.percentile(fa, 50), np.percentile(fa, 75), np.percentile(fa, 90), np.percentile(fa, 95), np.percentile(fa, 99),
               np.percentile(fb, 50), np.percentile(fb, 75), np.percentile(fb, 90), np.percentile(fb, 95), np.percentile(fb, 99)))
    print()
    print("對照：現行 factor 5.0 等於最低成交額 %s；factor 2.0 等於 %s" %
          ("{:,.0f}".format(5.0 * CAP0), "{:,.0f}".format(2.0 * CAP0)))
    print("  實際 dv1（T-1 成交額）分布：p50 %s  p10 %s  min %s" %
          ("{:,.0f}".format(np.percentile(ok["dv1"].dropna(), 50)),
           "{:,.0f}".format(np.percentile(ok["dv1"].dropna(), 10)),
           "{:,.0f}".format(ok["dv1"].dropna().min())))
    print()
