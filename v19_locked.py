# -*- coding: utf-8 -*-
r"""How often would the no-stop book be unable to close at 13:20?

Weni's objection to removing the stop is specific and it is not about the size of
the loss - it is about being forced to carry a short overnight and paying the
securities-lending cost for it. That only happens when the 13:20 force-clear
cannot fill, i.e. the stock is locked at the price limit at close. So the number
that decides the argument is not the tail PnL, it is the count of trades that end
the day locked.

A is the shipped book (SL 4%) and G is the candidate (no stop). Both are asked
the same question: at 13:25, is the settlement price sitting on the limit?
"""
import warnings; warnings.filterwarnings("ignore")
import collections
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
base = dict(liq=0.10, slip_scale=1.0, gap_max=0.04, gap_scale=1.0, exposure=1.00,
            order_cap=30, cost_mode="measured", gap_max_long=0.08, spread=0.00105,
            capture=True)
CASES = [("A SL 4%", dict(nosl=False, brake=((-0.006, .50), (-0.012, .25)))),
         ("G no SL", dict(nosl=True, brake=((-0.006, .45), (-0.012, .22))))]

d = T.D.copy()
d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
d["stock"] = d["stock"].astype(str)
lut = {(r["date"], r["stock"]): (float(r["lu"]), float(r["ld"]), float(r["day_close"]),
                                  float(r["tick"])) for _, r in d.iterrows()}
print("panel rows joined:", len(lut), flush=True)

for tag, kw in CASES:
    y = T.run(**dict(base, **kw))
    tr = pd.DataFrame([dict(zip("date code dir notional gross reason entry exit".split(), t))
                       for t in y["trades"]])
    tr["pnl"] = tr["notional"] * tr["gross"]
    info = tr.apply(lambda r: lut.get((r["date"], r["code"])), axis=1)
    tr["lu"] = [x[0] if x else np.nan for x in info]
    tr["ld"] = [x[1] if x else np.nan for x in info]
    tr["cl"] = [x[2] if x else np.nan for x in info]
    tr["tk"] = [x[3] if x else np.nan for x in info]
    ok = tr.dropna(subset=["lu"])
    # locked at close: SHORT cannot buy back at limit-up, LONG cannot sell at limit-down
    lock = ((ok["dir"] == "SHORT") & (ok["cl"] >= ok["lu"] - 1e-9)) | \
           ((ok["dir"] == "LONG") & (ok["cl"] <= ok["ld"] + 1e-9))
    n = len(ok); nl = int(lock.sum())
    sub = ok[lock]
    print("\n%s  n=%d" % (tag, n))
    print("  13:25 still locked (clear cannot fill): %d = %.2f%% of trades" % (nl, nl / n * 100))
    if nl:
        by_dir = collections.Counter(sub["dir"])
        by_year = collections.Counter(str(x)[:4] for x in sub["date"])
        print("  by direction:", dict(by_dir))
        print("  by year:", dict(sorted(by_year.items())))
        print("  PnL of those: total %.0f TWD, mean %+.2f%%, worst %+.2f%%"
              % (sub["pnl"].sum(), sub["gross"].mean() * 100, (sub["gross"] * 100).min()))
        print("  per trading day: %.3f" % (nl / max(1, ok["date"].nunique())))
