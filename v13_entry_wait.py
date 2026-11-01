"""How much does waiting cost? Entry at the open, or N minutes later.

Same orders, same lots, same exit engine. Only the entry minute moves. The point
is to turn "I cannot trade at 09:00:00" into a number: RISK1 measured the opening
print is readable ~10s after the open, and the live script needs a few more
seconds to size and send. So the honest question is not "open vs 09:01", it is
"what does each extra 30 seconds cost".

Entry at offset N = the close of the (09:00+N-1) bar, i.e. the price at 09:0N:00.
The exit scan starts at the bar AFTER the entry bar, so no bar is double-counted.

Usage: python v13_entry_wait.py
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from v13_engine import CAP0, COST, SLO, snap_price, run_backtest
import v13_sizing as S
from min_bars import bars_for

ORDER_CAP = 30
OFFSETS = [0, 1, 2, 3, 5, 10]
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
        path, vol = [], {}
        for b in bs:
            t = b[0][11:16]
            if "09:00" <= t <= "13:24":
                path.append((t, b[2], b[4], b[5], b[3]))
                vol[t] = b[1]
        if len(path) < 10 or path[0][0] != "09:00":
            continue
        e0 = path[0][1]
        if not e0 or e0 <= 0:
            continue
        lu = float(r["lu"]); ld = float(r["ld"]); tk = float(r["tick"]); tp = float(r["tp"])
        dr = r["direction"]; fc = float(r["day_close"]); sgn = -1.0 if dr == "SHORT" else 1.0
        notional = n * 1000.0 * e0
        v0 = vol.get("09:00", 0.0)
        out = {"date": day, "code": code, "dir": dr, "notional": notional,
               "gap": float(r["adj_gap"]), "mkt": float(r["market_ret"]), "open": e0,
               "flat0900": bool(path[0][2] == path[0][3]),
               "part0": notional / v0 if v0 > 0 else np.nan}
        for off in OFFSETS:
            hm = "09:%02d" % off if off else "09:00"   # price at 09:0N:00
            if off == 0:
                ent, scan = e0, path
            else:
                # Minutes with no trades have no bar. The price you would actually
                # get at 09:0N is the last print before it, so fall back to the
                # newest bar strictly before the target and scan from the next one.
                prior = [k for k, b in enumerate(path) if b[0] < hm]
                nxt = [k for k, b in enumerate(path) if b[0] >= hm]
                if not prior or not nxt:
                    out["pnl_%d" % off] = np.nan
                    continue
                ent = path[max(prior)][4]
                scan = path[min(nxt):]
            if ent <= 0:
                out["pnl_%d" % off] = np.nan
                continue
            x = walk(scan, ent, dr, lu, ld, tk, tp, fc)
            out["pnl_%d" % off] = sgn * (x - ent) / ent - 2 * COST
            out["ent_%d" % off] = ent
        rows.append(out)

R = pd.DataFrame(rows)
R = R[R["pnl_0"].notna()]
R.to_csv("D:/AI" + chr(0x5c08) + chr(0x6848) + "/StockAgent/DayTrading/entry_wait.csv",
         index=False, encoding="utf-8-sig")
print("orders: %d" % len(R))
for off in OFFSETS[1:]:
    print("  offset +%dm: %d orders have no readable price at that minute" %
          (off, int(R["pnl_%d" % off].isna().sum())))
print()
print("cost of waiting (net of cost, same lots)")
print("  %-8s %10s %10s %9s %11s %12s" % ("entry", "avg %", "p50 %", "win %", "total TWD", "vs open"))
base = (R["notional"] * R["pnl_0"]).sum()
print()
print("comparisons below use only the orders readable at BOTH minutes")
for off in OFFSETS:
    p = R["pnl_%d" % off]
    ok = p.notna(); tot = (R.loc[ok, "notional"] * p[ok]).sum()
    lbl = "09:00:00" if off == 0 else "+%d min" % off
    b = (R.loc[ok, "notional"] * R.loc[ok, "pnl_0"]).sum()
    print("  %-8s n=%4d %+9.3f %+10.3f %8.1f%% %11.0f %+11.0f (%+.1f%%)" %
          (lbl, int(ok.sum()), p[ok].mean() * 100, np.percentile(p[ok], 50) * 100,
           (p[ok] > 0).mean() * 100, tot, tot - b, (tot - b) / abs(b) * 100))
print()
for dr in ("SHORT", "LONG"):
    a = R[R["dir"] == dr]
    line = []
    b0 = (a["notional"] * a["pnl_0"]).sum()
    for off in OFFSETS[1:]:
        m = a["pnl_%d" % off].notna()
        t = (a.loc[m, "notional"] * a.loc[m, "pnl_%d" % off]).sum()
        b0m = (a.loc[m, "notional"] * a.loc[m, "pnl_0"]).sum()
        line.append("+%dm %+.0f%%" % (off, (t - b0m) / abs(b0m) * 100 if b0m else 0))
    print("  %-6s n=%4d  open profit %+9.0f   " % (dr, len(a), b0) + "  ".join(line))
