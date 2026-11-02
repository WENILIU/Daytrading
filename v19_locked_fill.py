# -*- coding: utf-8 -*-
r"""Can the 13:20 force-clear actually fill on the trades that end at a limit?

Both books settle ~6.4 pct of trades at a price sitting exactly on the price
limit. Daily bars cannot say whether a buy-back was possible there: a stock
printing the limit WITH volume had sellers, one pinned with no prints did not.
The 1-minute bars can. This is the operational question behind Weni's objection
("I am afraid it does not come back and I have to borrow"), and it applies to the
shipped book exactly as much as to the no-stop candidate - the locked population
is the same size in both (2,037 vs 2,043).

First attempt died with OSError(22) after 50 checks: it cached every bar of every
code it touched, and one code's file holds 50k rows. So: extract one date at a
time, keep nothing, and stream the CSV so a crash keeps what it earned.
"""
import warnings; warnings.filterwarnings("ignore")
import json, os, glob, pickle, time, collections, io
import numpy as np, pandas as pd
import v13_target as T

BUDGET_SEC = 420
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08, spread=0.00105,
            capture=True, nosl=True, brake=((-0.006, .45), (-0.012, .22)))
y = T.run(**base)
tr = pd.DataFrame([dict(zip("date code dir notional gross reason entry exit".split(), t))
                   for t in y["trades"]])
tr["pnl"] = tr["notional"] * tr["gross"]
d = T.D.copy()
d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
d["stock"] = d["stock"].astype(str)
lut = {(r["date"], r["stock"]): (float(r["lu"]), float(r["ld"]), float(r["day_close"]))
       for _, r in d.iterrows()}
info = tr.apply(lambda r: lut.get((r["date"], r["code"])), axis=1)
tr["lu"] = [x[0] if x else np.nan for x in info]
tr["ld"] = [x[1] if x else np.nan for x in info]
tr["cl"] = [x[2] if x else np.nan for x in info]
ok = tr.dropna(subset=["lu"]).copy()
lock = ok[((ok["dir"] == "SHORT") & (ok["cl"] >= ok["lu"] - 1e-9)) |
          ((ok["dir"] == "LONG") & (ok["cl"] <= ok["ld"] + 1e-9))].copy()
print("trades %d, locked at close %d (%.2f%%)" % (len(ok), len(lock), len(lock) / len(ok) * 100), flush=True)

idx = pickle.load(open("stock_1min_index.pkl", "rb"))
EPS = 1e-9
files_cache = {}


def dir_files(code):
    if code not in files_cache:
        p = idx.get(code)
        files_cache[code] = sorted(glob.glob(os.path.join(p, "*.json"))) if p and os.path.isdir(p) else []
    return files_cache[code]


def day_bars(code, date):
    """Bars for one (code, date). Filename is not the period, so the month-named
    file is only a fast path; every candidate is verified by the bar's own date."""
    want = {date}
    ordered = sorted(dir_files(code), key=lambda f: (date[:7] not in os.path.basename(f), f))
    for f in ordered:
        try:
            j = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        rows = j.get("data") if isinstance(j, dict) else j
        if not rows:
            continue
        hit = [r for r in rows if str(r.get("date", ""))[:10] == date]
        if hit:
            hit.sort(key=lambda r: str(r.get("date")))
            return hit
    return []


out = io.open("_locked_fill.csv", "w", encoding="utf-8", newline="")
w = csv_cols = None
res = []
t0 = time.time()
lock = lock.sort_values("date", ascending=False)
for _, r in lock.iterrows():
    if time.time() - t0 > BUDGET_SEC:
        print("budget reached", flush=True)
        break
    day = day_bars(r["code"], r["date"])
    if not day:
        continue
    short = r["dir"] == "SHORT"
    lim = r["lu"] if short else r["ld"]
    win = [b for b in day if "13:10" <= str(b["date"])[11:16] < "13:25"]
    if not win:
        continue
    at = [b for b in win if b.get("volume", 0) > 0 and
          (b["high"] >= lim - EPS if short else b["low"] <= lim + EPS)]
    filled = len(at) > 0
    res.append(dict(date=r["date"], code=r["code"], dir=r["dir"], pnl=r["pnl"],
                    gross=r["gross"], filled=filled, prints=len(at),
                    vol_at_limit=sum(b.get("volume", 0) for b in at)))
    if w is None:
        w = csv_cols = list(res[-1].keys())
        out.write(",".join(csv_cols) + "\n")
    out.write(",".join(str(x) for x in res[-1].values()) + "\n")
    out.flush()
    if len(res) % 25 == 0:
        print("  %d checked, %.0fs, fillable %.1f%%"
              % (len(res), time.time() - t0, np.mean([x["filled"] for x in res]) * 100), flush=True)
out.close()

df = pd.DataFrame(res)
print("\nchecked with 1-min data: %d of %d locked" % (len(df), len(lock)), flush=True)
if len(df):
    n = len(df); nf = int(df["filled"].sum())
    print("clear WOULD fill at the limit: %d = %.1f%%" % (nf, nf / n * 100))
    print("could NOT fill (forced overnight): %d = %.1f%%" % (n - nf, (n - nf) / n * 100))
    for k, g in df.groupby("filled"):
        print("  filled=%s n=%d by dir %s, pnl total %.0f TWD, mean %+.2f%%"
              % (k, len(g), dict(collections.Counter(g["dir"])), g["pnl"].sum(),
                 (g["gross"] * 100).mean()))
    print("  by year:", dict(sorted(collections.Counter(str(x)[:4] for x in df[~df["filled"]]["date"]).items())))
