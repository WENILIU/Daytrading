# -*- coding: utf-8 -*-
r"""Split the limit-touch stops into "released" and "locked to the close".

The shipped book stops a SHORT the moment the price reaches lu - 1 tick, and a
LONG the moment it reaches ld + 1 tick. Relaxing that is worth +21 pct on
2022-2026, but a daily bar cannot tell a touch that released from a lock that
held to the close - and a lock genuinely cannot be exited at 13:25, so "hold to
the close" is an upper bound rather than a rule.

This reads the 1-minute bars for exactly the trades the shipped book stops out on
a price limit and answers four questions:

  1. coverage. Availability must come from the bar "date" field, not the
     filename: 2330_2025-01.json holds all of 2025 (verified 2026-11-02).
  2. how often the limit releases, and how long it takes.
  3. three exit rules on the same trades:
       R0 shipped : stop at the limit-bound price the moment it is reached.
       R1 upper   : ignore the lock risk, settle at the 13:25 price.
       R2(X) rule : after the touch rest a limit order X pct back from the
                    limit. It fills only if the price comes back; if the stock
                    stays locked the order never fills and the outcome equals
                    R0. A resting LIMIT order is used deliberately - it cannot
                    fill worse than its price, which is what makes R2 something
                    that can actually be submitted rather than a hope.
  4. what the locked ones really cost - the next day's open and close, because a
     short that cannot be covered at limit-up becomes an overnight position.

R2 is priced at the trigger level, the best a resting limit order can do; the
real fill can only be better. R0 is itself optimistic for the locked cases: a
buy order one tick under a locked limit-up sits behind the queue and does not
fill at all, so its booked price is not a price that was obtainable.
"""
import warnings; warnings.filterwarnings("ignore")
import os, json, collections
import numpy as np, pandas as pd
import v13_target as T
from v13_engine import snap_price, SLO

STOPS = pd.read_pickle("_min1_all_stops.pkl")
IDX = pd.read_pickle("stock_1min_index.pkl")
XS = (0.005, 0.01, 0.015, 0.02, 0.03)
CUT = "13:25"

need = collections.defaultdict(set)
for d, code, direction, reason, notional, gross in STOPS:
    need[str(code)].add(str(d))
print("觸板停損 %d 筆，涉及 %d 檔股票" % (len(STOPS), len(need)), flush=True)

INFO = {}
keyset = set((str(d), str(c)) for d, c, *_ in STOPS)
for _, r in T.D.iterrows():
    k = (str(pd.Timestamp(r["date"]).date()), str(r["stock"]))
    if k in keyset:
        INFO[k] = (float(r["entry"]), float(r["lu"]), float(r["ld"]),
                   float(r["tick"]), float(r["tp"]))


def load(code, dates):
    """All dates present for `code`; full bars only for `dates`."""
    folder = IDX.get(str(code))
    if not folder or not os.path.isdir(folder):
        return {}, {}
    bars, edge = {}, {}
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".json"):
            continue
        try:
            rows = json.load(open(os.path.join(folder, fn), encoding="utf-8"))["data"]
        except Exception:
            continue
        for b in rows:
            ds = str(b["date"])[:10]
            tm = str(b["date"])[11:16]
            o, h, l, c = (float(b["open"]), float(b["high"]),
                          float(b["low"]), float(b["close"]))
            e = edge.setdefault(ds, [None, None, None, None])
            if e[0] is None or tm < e[0]:
                e[0], e[1] = tm, o
            if e[2] is None or tm > e[2]:
                e[2], e[3] = tm, c
            if ds in dates:
                bars.setdefault(ds, []).append((tm, h, l, c))
    for ds in bars:
        bars[ds].sort(key=lambda x: x[0])
    return bars, edge


rows = []
codes = sorted(need.keys())
for i, code in enumerate(codes):
    if i % 20 == 0:
        print("   %d/%d %s" % (i, len(codes), code), flush=True)
    bars, edge = load(code, need[code])
    for (d, c, direction, reason, notional, gross) in STOPS:
        if str(c) != code:
            continue
        ds = str(d)
        k = (ds, code)
        if k not in INFO or ds not in bars:
            continue
        entry, lu, ld, tk, tp = INFO[k]
        seq = bars[ds]
        if direction == "SHORT":
            lim, side = lu, 1.0
            slp = min(snap_price(entry * (1 + SLO)), round(lu - tk, 2))
        else:
            lim, ld_ = ld, -1.0
            side = -1.0
            slp = max(snap_price(entry * (1 - SLO)), round(ld + tk, 2))
        touch = None
        for j, (t, h, l, cl) in enumerate(seq):
            if side > 0 and h >= slp - 1e-9:
                touch = j; break
            if side < 0 and l <= slp + 1e-9:
                touch = j; break
        if touch is None:
            continue
        pre = [b for b in seq if b[0] <= CUT]
        if not pre:
            continue
        close_1325 = pre[-1][3]
        last = seq[-1][3]
        locked = (last >= lim - tk - 1e-9) if side > 0 else (last <= lim + tk + 1e-9)
        rec = dict(date=ds, code=code, direction=direction, notional=float(notional),
                   entry=entry, lim=lim, slp=slp, tick=tk, touch_time=seq[touch][0],
                   locked=bool(locked), close_1325=close_1325,
                   r0=(entry - slp) / entry if side > 0 else (slp - entry) / entry,
                   r1=(entry - close_1325) / entry if side > 0 else (close_1325 - entry) / entry)
        for X in XS:
            trig = lim * (1 - side * X)
            hit = ""
            for j in range(touch + 1, len(seq)):
                if side > 0 and seq[j][2] <= trig + 1e-9:
                    hit = seq[j][0]; break
                if side < 0 and seq[j][1] >= trig - 1e-9:
                    hit = seq[j][0]; break
            px = slp if not hit else trig
            rec["r2_%.3f" % X] = (entry - px) / entry if side > 0 else (px - entry) / entry
            rec["hit_%.3f" % X] = hit
        # overnight: the next date this stock has bars for
        nxt = sorted(x for x in edge if x > ds)
        if nxt:
            e = edge[nxt[0]]
            rec["nd_open"] = e[1]; rec["nd_close"] = e[3]; rec["nd_date"] = nxt[0]
        else:
            rec["nd_open"] = np.nan; rec["nd_close"] = np.nan; rec["nd_date"] = ""
        rows.append(rec)

df = pd.DataFrame(rows)
pd.to_pickle(df, "_min1_lock.pkl")
print("\n可分析：%d / %d 筆（%.1f%%）" % (len(df), len(STOPS), len(df) / len(STOPS) * 100), flush=True)
if not len(df):
    raise SystemExit(0)
df["year"] = [x[:4] for x in df["date"]]
print("涉及股票 %d 檔；年份 %s" % (df["code"].nunique(), sorted(df["year"].unique())))
print("\n鎖到收盤 vs 曾解開：")
print("   鎖到收盤  %5d  %5.1f%%" % (df["locked"].sum(), df["locked"].mean() * 100))
print("   曾解開    %5d  %5.1f%%" % ((~df["locked"]).sum(), (1 - df["locked"].mean()) * 100))
print("\n逐年（筆數 / 鎖死占比 / 觸板時間中位）：")
for y, g in df.groupby("year"):
    print("   %s  n=%4d  鎖死 %5.1f%%  觸板中位 %s"
          % (y, len(g), g["locked"].mean() * 100, sorted(g["touch_time"])[len(g) // 2]), flush=True)
