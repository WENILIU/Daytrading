# -*- coding: utf-8 -*-
r"""Is there lead time before a short gets pinned?

Every countermeasure against being locked at the limit assumes the lock is foreseeable
while the market is still open. That has never been measured. This measures it: for the
shorts the backtest actually pinned (day_close >= the upper limit, the same test the
engine uses to charge the pin cost), load the 1-minute path and record the first time the
price came within 2.0 / 1.0 / 0.5 pct of the upper limit, and how much of the eventual
loss had already been incurred at 11:00 and 13:00.

If those times cluster at 13:15 no rule can act on them and the idea is dead. If they
cluster before 11:00 there is hours of warning and a cheap exit exists.

1-minute bars live in two layouts: <code>_YYYY-MM.json (2023-05, 2024-01, 2025-01,
2026-01) and <code>_YYYY-MM-DD.json (2025-03..2025-10), and each file holds a rolling
window of dates rather than only its own, so every file matching the month is scanned and
the rows filtered to the target day.
"""
import warnings; warnings.filterwarnings("ignore")
import pickle, os, json, glob
import numpy as np, pandas as pd
import v13_target as T

PIN = 0.03149 + 0.0015 + 0.30 * 2 / 365.0
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00,
            gap_max_long=0.08, spread=0.00105, cost_mode="measured",
            brake=((-0.008, .50), (-0.016, .25)), gap_max=0.040, order_cap=20,
            nosl=True, pin_short=PIN, pin_long=0.0)
y = T.run(**dict(base, capture=True))
tr = pd.DataFrame(y["trades"], columns=["date", "code", "direction", "notional",
                                        "gross", "reason", "entry", "exit"])
tr["date"] = pd.to_datetime(tr["date"]); tr["code"] = tr["code"].astype(str)
key = T.D.set_index(["date", T.D["stock"].astype(str)])[["lu", "day_close"]]
tr = tr.join(key, on=["date", "code"])
pin = tr[(tr["direction"] == "SHORT") & (tr["day_close"] >= tr["lu"] - 1e-9)].copy()
print("pinned shorts (day_close >= limit-up):", len(pin), flush=True)

IDX = pickle.load(open("stock_1min_index.pkl", "rb"))
CACHE = {}
def bars(code, day):
    k = (code, day.strftime("%Y-%m"))
    if k not in CACHE:
        rows = []
        d = IDX.get(code)
        if d:
            for f in glob.glob(os.path.join(d, "%s_%s*.json" % (code, day.strftime("%Y-%m")))):
                try:
                    raw = json.load(open(f, encoding="utf-8", errors="replace"))
                except Exception:
                    continue
                data = raw.get("data", []) if isinstance(raw, dict) else raw
                rows += [b for b in data if str(b.get("date", ""))[:10] == day.strftime("%Y-%m-%d")]
        CACHE[k] = pd.DataFrame(rows)
    return CACHE[k]

recs = []
for _, r in pin.iterrows():
    b = bars(r["code"], r["date"])
    if b.empty or "high" not in b.columns:
        continue
    b["t"] = pd.to_datetime(b["date"], utc=True).dt.tz_convert("Asia/Taipei").dt.tz_localize(None)
    b = b.sort_values("t")
    lu = float(r["lu"]); ent = float(r["entry"])
    if not (lu > 0 and ent > 0) or b["t"].dt.date.nunique() != 1:
        continue
    mins = lambda t: int(t.hour * 60 + t.minute) - 540
    rec = dict(date=r["date"], code=r["code"], entry=ent, lu=lu, gross=r["gross"],
               final_loss=(lu - ent) / ent * 100)
    for tag, thr in [("t_2p0", 0.980), ("t_1p0", 0.990), ("t_0p5", 0.995), ("t_touch", 1.000)]:
        m = b[b["high"] >= lu * thr]
        rec[tag] = mins(m["t"].min()) if len(m) else -1
    # how much of the loss was already there earlier in the day
    for tag, hhmm in [("loss_1100", 11 * 60), ("loss_1300", 13 * 60)]:
        m = b[b["t"].dt.hour * 60 + b["t"].dt.minute <= hhmm]
        rec[tag] = (float(m["close"].iloc[-1]) - ent) / ent * 100 if len(m) else np.nan
    recs.append(rec)
R = pd.DataFrame(recs)
print("\nreadable 1m paths:", len(R), flush=True)
R["ym"] = R["date"].dt.strftime("%Y-%m")
print("months:", dict(R["ym"].value_counts().sort_index()), flush=True)
def hhmm(v):
    v = 540 + v; return "%02d:%02d" % (v // 60, v % 60)
print("\n=== 鎖死放空：第一次逼近漲停的時間 ===", flush=True)
for tag, lbl in [("t_2p0", "距漲停2%"), ("t_1p0", "距漲停1%"), ("t_0p5", "距漲停0.5%"), ("t_touch", "觸及漲停")]:
    s = R[R[tag] >= 0][tag]
    if len(s) == 0:
        print("%-9s 從未觸及" % lbl, flush=True); continue
    print("%-9s 觸及 %3d/%3d  首次 p10 %s  p50 %s  p90 %s"
          % (lbl, len(s), len(R), hhmm(np.percentile(s, 10)), hhmm(np.percentile(s, 50)),
             hhmm(np.percentile(s, 90))), flush=True)
print("\n=== 虧損何時已經形成（相對於開盤進價，%）===", flush=True)
for tag, lbl in [("loss_1100", "11:00 時"), ("loss_1300", "13:00 時"), ("final_loss", "收盤鎖在漲停")]:
    s = R[tag].dropna()
    print("%-12s p50 %+6.2f%%  p90 %+6.2f%%  已有虧損的比例 %5.1f%%"
          % (lbl, np.percentile(s, 50), np.percentile(s, 90), (s > 0).mean() * 100), flush=True)
R.to_csv("_pinlead.csv", index=False)
print("saved _pinlead.csv", flush=True)
