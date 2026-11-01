"""A/B test: enter at the opening auction print, or at 09:01?

Both arms walk the SAME minute path with the SAME exit rule (TP/SL snapped to
legal prices, SL capped by the price limit, force close at the closing auction).
Only `entry` differs, and the lot count is held identical on purpose - so the
money difference is the entry price and nothing else.

  A  entry = the 09:00 bar open. Bars are START-labelled, so that IS the
     exchange opening print (verified equal to the backtest entry on 1,412/1,413
     orders). The exit scan starts at the 09:00 bar: everything in that bar
     happens after the auction print, so a stop can legitimately be hit there.
  B  entry = the 09:00 bar close = the price at 09:01:00. Scan starts at 09:01.
  B2 entry = the 09:01 bar open (first trade after 09:01:00). Sensitivity check
     on how B is defined; if B and B2 agree, B is not an artefact of one bar.

Force close uses day_close from the signal table, which was verified identical to
the closing-auction print on 1,501/1,501 orders. That makes arm A reproduce the
backtest, and the agreement rate printed at the end is the check on that.

Sizing is v13_sizing.R9 exactly as the live script uses it (dv_cap = K_OPEN x
10 pct of T-1 turnover, no min_turnover_factor). SLO is v13_engine.SLO.

Usage: python v13_entry_ab.py
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from v13_engine import CAP0, COST, SLO, snap_price, exit_of_legal, run_backtest
import v13_sizing as S
from min_bars import bars_for

ORDER_CAP = 30
CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
_, got, _ = run_backtest(capture=("2023-01-01", "2026-12-31"), capital=CAP0, **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)


def walk(bars, entry, direction, lu, ld, tick, tp, fc):
    """First touch of TP then SL over the minute path, else the closing auction.

    bars is the list to scan; the caller decides whether the entry bar is inside
    it. TP is checked before SL inside a bar, which is the same optimistic
    ordering the day-level engine uses, so the two arms stay comparable.
    """
    if direction == "SHORT":
        tpp = snap_price(entry * (1 - tp))
        slp = min(snap_price(entry * (1 + SLO)), round(lu - tick, 2))
        for t, o, h, l, c in bars:
            if l <= tpp:
                return tpp, "TP"
            if h >= slp:
                return slp, "SL"
    else:
        tpp = snap_price(entry * (1 + tp))
        slp = max(snap_price(entry * (1 - SLO)), round(ld + tick, 2))
        for t, o, h, l, c in bars:
            if h >= tpp:
                return tpp, "TP"
            if l <= slp:
                return slp, "SL"
    return fc, "FC"


rows = []
for d, g in D.groupby("date"):
    g = g.sort_values("_rank"); rem = CAP0; n_day = 0
    day = str(pd.Timestamp(d).date())
    for _, r in g.iterrows():
        if n_day >= ORDER_CAP:
            break
        pr = float(r["entry"]); code = str(r["stock"])
        dv1 = float(TO1.at[d, code]) if (code in TO1.columns and d in TO1.index) else np.nan
        n = S.lots_for(S.R9, float(r["_weight"]), pr, rem, dv1, capital=CAP0)
        if n <= 0:
            continue
        rem -= n * 1000.0 * pr; n_day += 1
        bs = bars_for(code, day)
        if not bs:
            continue
        path, vol = [], {}
        for b in bs:
            t = b[0][11:16]
            if "09:00" <= t <= "13:24":
                path.append((t, b[2], b[4], b[5], b[3]))
                vol[t] = b[1]
        if len(path) < 10:
            continue
        path.sort()
        if path[0][0] != "09:00":
            continue
        e0 = path[0][1]                                   # opening auction print
        e1 = path[0][4]                                   # price at 09:01:00
        e2 = path[1][1] if len(path) > 1 else None        # first trade after 09:01
        if not e0 or e0 <= 0 or not e1 or e1 <= 0:
            continue
        lu = float(r["lu"]); ld = float(r["ld"]); tk = float(r["tick"]); tp = float(r["tp"])
        dr = r["direction"]; fc = float(r["day_close"]); sgn = -1.0 if dr == "SHORT" else 1.0
        notional = n * 1000.0 * e0
        v0 = vol.get("09:00", 0.0); v1 = vol.get("09:01", 0.0)
        # arm A reproduced on the day-level OHLC, for the agreement check
        _, _, _, why_day, gross_day = exit_of_legal(dr, e0, float(r["day_high"]),
                                                   float(r["day_low"]), fc, lu, ld, tk, tp)
        out = {"date": day, "code": code, "dir": dr, "lots": n, "notional": notional,
               "gap": float(r["adj_gap"]), "mkt": float(r["market_ret"]),
               "open": e0, "e0901": e1, "flat0900": bool(path[0][2] == path[0][3]),
               "part0": notional / v0 if v0 > 0 else np.nan,
               "part1": notional / (v0 + v1) if v0 + v1 > 0 else np.nan,
               "why_day": why_day, "gross_day": gross_day}
        for tag, ent, scan in (("A", e0, path), ("B", e1, path[1:]),
                               ("B2", e2 if e2 and e2 > 0 else e1, path[1:])):
            x, why = walk(scan, ent, dr, lu, ld, tk, tp, fc)
            out["pnl_" + tag] = sgn * (x - ent) / ent - 2 * COST
            out["why_" + tag] = why
        rows.append(out)

R = pd.DataFrame(rows)
R.to_csv("D:\\AI\u5c08\u6848\\StockAgent\\DayTrading\\entry_ab.csv", index=False, encoding="utf-8-sig")
print("orders compared: %d" % len(R))

R["money_A"] = R["notional"] * R["pnl_A"]
R["money_B"] = R["notional"] * R["pnl_B"]
R["delta"] = R["money_B"] - R["money_A"]

print()
print("=== 1. per-order net of cost ===")
for tag, lbl in (("A", "A  entry = opening auction print"),
                 ("B", "B  entry = 09:01:00 price"),
                 ("B2", "B2 entry = first trade after 09:01")):
    a = R["pnl_" + tag] * 100
    print("  %-32s avg %+6.3f%%  p50 %+6.3f%%  win %5.1f%%  worst %+6.2f%%" %
          (lbl, a.mean(), np.percentile(a, 50), (a > 0).mean() * 100, a.min()))

print()
print("=== 2. money at 4.5M, same lots ===")
print("  A total %+.0f TWD    B total %+.0f TWD    B-A %+.0f TWD (%.2f%% of capital)" %
      (R["money_A"].sum(), R["money_B"].sum(), R["delta"].sum(),
       R["delta"].sum() / CAP0 * 100))
print("  B better on %.1f%% of orders" % ((R["delta"] > 0).mean() * 100))
for dr in ("SHORT", "LONG"):
    a = R[R["dir"] == dr]
    print("  %-6s n=%5d  A %+.0f  B %+.0f  B-A %+.0f  (per order %+.0f)" %
          (dr, len(a), a["money_A"].sum(), a["money_B"].sum(), a["delta"].sum(),
           a["delta"].mean()))

print()
print("=== 3. by year ===")
R["year"] = R["date"].str[:4]
for y, g in R.groupby("year"):
    print("  %s n=%4d  A %+9.0f  B %+9.0f  B-A %+9.0f  = %+.2f%% of 4.5M" %
          (y, len(g), g["money_A"].sum(), g["money_B"].sum(), g["delta"].sum(),
           g["delta"].sum() / CAP0 * 100))

print()
print("=== 4. slippage by signal strength (this is the decision) ===")
R["slip"] = (R["e0901"] / R["open"] - 1.0)
for lo, hi, lbl in ((0, .05, "|gap| 0-5%"), (.05, .07, "|gap| 5-7%"),
                    (.07, .10, "|gap| 7-10%")):
    a = R[(R["gap"].abs() >= lo) & (R["gap"].abs() < hi)]
    if len(a) == 0:
        continue
    print("  %-12s n=%5d  adverse move to 09:01 avg %+.3f%%  p90 %+.3f%%  cost LONG %+.3f%% SHORT %+.3f%%" %
          (lbl, len(a), a["slip"].mean() * 100, np.percentile(a["slip"], 90) * 100,
           a[a["dir"] == "LONG"]["slip"].mean() * 100,
           -a[a["dir"] == "SHORT"]["slip"].mean() * 100))
print()
for lo, hi, lbl in ((-9, -.02, "market gap < -2%"), (-.02, .02, "market flat"),
                    (.02, 9, "market gap > +2%")):
    a = R[(R["mkt"] >= lo) & (R["mkt"] < hi)]
    if len(a) == 0:
        continue
    print("  %-18s n=%5d  adverse avg %+.3f%%  p90 %+.3f%%" %
          (lbl, len(a), a["slip"].mean() * 100, np.percentile(a["slip"], 90) * 100))

print()
print("=== 5. can the order actually be filled? ===")
print("  09:00 bar high==low (only the auction printed, no continuous trading):")
print("     %d orders (%.1f%%) - for these B is identical to A by construction" %
      (R["flat0900"].sum(), R["flat0900"].mean() * 100))
for p in (0.05, 0.10, 0.20):
    print("  participation vs 09:00 bar value > %.0f%%: %4d orders (%.1f%%)" %
          (p * 100, (R["part0"] > p).sum(), (R["part0"] > p).mean() * 100))
print("  participation vs value traded through 09:01 > 5%%: %4d (%.1f%%)  > 10%%: %4d (%.1f%%)" %
      ((R["part1"] > .05).sum(), (R["part1"] > .05).mean() * 100,
       (R["part1"] > .10).sum(), (R["part1"] > .10).mean() * 100))
print("  order size: p50 %.0f TWD  p90 %.0f  max %.0f  (capital 4.5M)" %
      (np.percentile(R["notional"], 50), np.percentile(R["notional"], 90), R["notional"].max()))
print("  B is worse than A on %.1f%% of orders; median per-order gap %+.0f TWD" %
      ((R["delta"] < 0).mean() * 100, np.percentile(R["delta"], 50)))
print("  participation p50 %.2f%%  p90 %.2f%%  p99 %.2f%%" %
      (np.percentile(R["part0"].dropna(), 50) * 100,
       np.percentile(R["part0"].dropna(), 90) * 100,
       np.percentile(R["part0"].dropna(), 99) * 100))

print()
print("=== 6. agreement check: arm A minute-walk vs the day-level engine ===")
MAP = {"停利 TP": "TP", "停損 SL": "SL", "停損(觸漲停上限)": "SL", "停損(觸跌停下限)": "SL",
       "13:25 強制平倉": "FC"}
same = (R["why_A"] == R["why_day"].map(MAP))
print("  exit reason identical: %.1f%%" % (same.mean() * 100))
print("  disagreements:", pd.crosstab(R["why_day"].map(MAP), R["why_A"]).to_dict())
print("  PnL difference: mean %+.4f%%  p90abs %.4f%%" %
      (((R["pnl_A"] + 2 * COST) - R["gross_day"]).mean() * 100,
       np.percentile(((R["pnl_A"] + 2 * COST) - R["gross_day"]).abs(), 90) * 100))
print("  A:", R["why_A"].value_counts().to_dict())
print("  B:", R["why_B"].value_counts().to_dict())
