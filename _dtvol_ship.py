"""Ship the day-trade "not traded lately" list to the live data directory.

Shipped as {date: [codes]} rather than the 60MB panel: the live path only ever asks
"which names were not day traded before today", and a 60MB frame read at 09:00 is time
spent doing nothing. The rolling sum is computed here, once, with the same shift(1) the
measurement used, so the live answer and the measured cost cannot drift apart.
"""
import os, pickle, time, pandas as pd

N = 20
p = pd.read_pickle("_dtvol_panel.pkl")
dead = (p.fillna(0).rolling(N, min_periods=N).sum().shift(1) <= 0)
out = {}
for d, row in dead.iterrows():
    hit = [c for c in row.index[row.values]]
    if hit:
        out[str(pd.Timestamp(d).date())] = hit
dst = r"D:\gapfade_data\daytrade_dead_list.pkl"
pickle.dump({"sessions": N, "asof": str(pd.Timestamp(p.index[-1]).date()), "days": out},
            open(dst, "wb"))
print("shipped", dst, "| days", len(out), "| bytes", os.path.getsize(dst))
t0 = time.time()
r = pickle.load(open(dst, "rb"))
print("reload", f"{time.time()-t0:.3f}s", "| last day", max(r["days"]), "| codes that day", len(r["days"][max(r["days"])]))
