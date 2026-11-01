"""Arm C: after seeing the open, post a limit AT the opening print and wait.

Arms A and B are the two ends of the same problem: A gets the price but must
commit before knowing it, B knows everything but pays the move. A limit at the
opening print is the middle path, and it is a normal order the broker accepts
after 09:00 - no pre-auction qualification needed.

Mechanics, deliberately conservative:
  - the order is placed at 09:01:00, i.e. after reading the open and the first
    minute, so it cannot be an auction order
  - LONG buys at the open price only when a later bar TRIPS that price (low <=
    open); SHORT sells at the open only when high >= open
  - the fill is assumed at exactly the limit price. A real limit at the touch can
    be queued behind others; that is the optimistic part of this arm
  - unfilled within the window = no trade, and the capital stays idle
  - after filling, the exit scan starts at the bar AFTER the fill bar
Usage: python v13_entry_limit.py
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from v13_engine import CAP0, COST, SLO, snap_price, run_backtest
import v13_sizing as S
from min_bars import bars_for

ORDER_CAP = 30
WINDOWS = [5, 15, 30, 75]          # minutes the limit is left working
CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
_, got, _ = run_backtest(capture=("2023-01-01", "2026-12-31"), capital=CAP0, **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)


def walk(bars, entry, direction, lu, ld, tick, tp, fc):
    if direction == "SHORT":
        tpp = snap_price(entry * (1 - tp))
        slp = min(snap_price(entry * (1 + SLO)), round(lu - tick, 2))
        for t, o, h, l, c in bars:
            if l <= tpp:
                return tpp
            if h >= slp:
                return slp
    else:
        tpp = snap_price(entry * (1 + tp))
        slp = max(snap_price(entry * (1 - SLO)), round(ld + tick, 2))
        for t, o, h, l, c in bars:
            if h >= tpp:
                return tpp
            if l <= slp:
                return slp
    return fc


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
        path = []
        for b in bs:
            t = b[0][11:16]
            if "09:00" <= t <= "13:24":
                path.append((t, b[2], b[4], b[5], b[3]))
        if len(path) < 10 or path[0][0] != "09:00":
            continue
        path.sort()
        e0 = path[0][1]
        if not e0 or e0 <= 0:
            continue
        lu = float(r["lu"]); ld = float(r["ld"]); tk = float(r["tick"]); tp = float(r["tp"])
        dr = r["direction"]; fc = float(r["day_close"]); sgn = -1.0 if dr == "SHORT" else 1.0
        notional = n * 1000.0 * e0
        out = {"date": day, "code": code, "dir": dr, "notional": notional,
               "gap": float(r["adj_gap"])}
        # arm B for reference: market at 09:01
        e1 = path[0][4]
        out["pnl_B"] = (sgn * (walk(path[1:], e1, dr, lu, ld, tk, tp, fc) - e1) / e1 - 2 * COST
                        if e1 and e1 > 0 else np.nan)
        # arm A for reference
        out["pnl_A"] = sgn * (walk(path, e0, dr, lu, ld, tk, tp, fc) - e0) / e0 - 2 * COST
        # arm C: limit at the opening print, filled only when the market comes back
        for w in WINDOWS:
            hit = None
            for k in range(1, len(path)):
                hm = path[k][0]
                mins = (int(hm[:2]) - 9) * 60 + int(hm[3:]) - 1
                if mins >= w:   # exactly w minutes after 09:01
                    break
                if (dr == "LONG" and path[k][3] <= e0) or (dr == "SHORT" and path[k][2] >= e0):
                    hit = k
                    break
            if hit is None:
                out["pnl_C%d" % w] = 0.0        # no trade, no PnL, no cost
                out["fill_C%d" % w] = 0
            else:
                out["pnl_C%d" % w] = sgn * (walk(path[hit + 1:], e0, dr, lu, ld, tk, tp, fc) - e0) / e0 - 2 * COST
                out["fill_C%d" % w] = 1
        rows.append(out)

R = pd.DataFrame(rows)
R = R[R["pnl_B"].notna()]
R.to_csv("D:/AI" + chr(0x5c08) + chr(0x6848) + "/StockAgent/DayTrading/entry_limit.csv",
         index=False, encoding="utf-8-sig")
print("orders: %d" % len(R))
print()
print("=== arm C: post a limit at the opening print at 09:01 ===")
bA = (R["notional"] * R["pnl_A"]).sum(); bB = (R["notional"] * R["pnl_B"]).sum()
print("  A market at open : fill 100.0%%  profit %+10.0f" % bA)
print("  B market at 09:01: fill 100.0%%  profit %+10.0f  (%+.1f%% vs A)" %
      (bB, (bB - bA) / abs(bA) * 100))
for w in WINDOWS:
    t = (R["notional"] * R["pnl_C%d" % w]).sum()
    f = R["fill_C%d" % w].mean() * 100
    per = R.loc[R["fill_C%d" % w] == 1, "pnl_C%d" % w]
    print("  C limit at open, wait %-2dm: fill %5.1f%%  profit %+10.0f  (%+.1f%% vs A)  per filled order %+.3f%%" %
          (w, f, t, (t - bA) / abs(bA) * 100, per.mean() * 100))
print()
print("=== fill rate by direction and gap size (window 30 min) ===")
for dr in ("SHORT", "LONG"):
    a = R[R["dir"] == dr]
    print("  %-6s n=%4d  fill %.1f%%" % (dr, len(a), a["fill_C30"].mean() * 100))
for lo, hi, lbl in ((0, .05, "|gap| <5%"), (.05, .07, "|gap| 5-7%"), (.07, 1, "|gap| >=7%")):
    a = R[(R["gap"].abs() >= lo) & (R["gap"].abs() < hi)]
    if len(a):
        print("  %-12s n=%4d  fill %.1f%%" % (lbl, len(a), a["fill_C30"].mean() * 100))
