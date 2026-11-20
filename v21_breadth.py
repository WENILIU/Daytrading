import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]: os.environ[k]="1"
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

S, E = "2023-05-23", "2026-12-31"
D = T.D.copy(); D["_d"] = pd.to_datetime(D["date"])
MON = D[(D["_d"] >= pd.Timestamp(S)) & (D["_d"] <= pd.Timestamp(E))]

# breadth gate = price_dir < TH. QMIN is NOT binding (verified) -> drop it.
THGRID = [-0.012, -0.010, -0.008, -0.006]
SIZEGRID = [1.5, 2.0, 2.6, 3.0, 3.5, 4.0]

# ---- build real 09:01 open-volume matrix ONCE over the loosest superset ----
sup = MON[(~MON["blocked"].values) & (MON["price_dir"] < max(THGRID))]
pairs = [(str(s).zfill(4), str(pd.Timestamp(d).date())) for d, s in zip(sup["date"], sup["stock"])]
print("building open-volume matrix for %d pairs / %d codes ..." % (len(pairs), sup["stock"].nunique()), flush=True)
FV = T.build_open_volume_matrix(pairs)
print("FV done:", FV.shape, "nonzero", int((FV.values>0).sum()), flush=True)

def gate(th):
    b = MON[(~MON["blocked"].values) & (MON["price_dir"] < th)]
    return b

def runone(b, size):
    T.GROUPS = {d: g for d, g in b.groupby("date")}; T.days = sorted(b["date"].unique())
    T.TO1 = FV; T.K_OPEN = 1.0
    r = T.run(slip_scale=1.0, date_min=S, s3=False, size_scale=size, exposure=1.0,
              gap_max=0.08, zt_min_dist=0.014, liq=T.REAL_OPEN_CAP,
              brake=((-0.03,0.30),(-0.06,0.12)), capture=True)
    y = r["yearly"]; rets = [y[k]/T.CAP0*100 for k in sorted(y)]
    return dict(mdd=r["mdd"], avg=float(np.mean(rets)), worst=float(min(rets)),
                per_day=r["per_day"], med=float(np.median(rets)), yrs={k:round(v,1) for k,v in zip(sorted(y),rets)})

print("")
print("%-9s %-6s %8s %9s %9s %8s %8s" % ("TH","size","MDD%","AVG%","WORSTYR%","PERDAY","MED%"))
print("-"*72)
best = {}
for th in THGRID:
    b = gate(th)
    for sz in SIZEGRID:
        try:
            o = runone(b, sz)
        except Exception as ex:
            print("%-9s %-6s  ERR %s" % (("%g"%th), ("%g"%sz), ex), flush=True); continue
        print("%-9s %-6s %8.2f %9.1f %9.1f %8.2f %8.1f" % (("%g"%th),("%g"%sz),o["mdd"],o["avg"],o["worst"],o["per_day"],o["med"]), flush=True)
        if o["mdd"] >= -4.5:
            if th not in best or o["avg"] > best[th]["avg"]:
                best[th] = dict(size=sz, **o)
    print("", flush=True)

print("=== BEST per breadth under MDD >= -4.5% (red line -5.0%) ===")
print("%-9s %6s %9s %9s %8s" % ("TH","size","AVG%","WORSTYR%","PERDAY"))
for th in THGRID:
    if th in best:
        o=best[th]; print("%-9g %6g %9.1f %9.1f %8.2f" % (th,o["size"],o["avg"],o["worst"],o["per_day"]), flush=True)
    else:
        print("%-9g  none holds MDD>=-4.5" % th, flush=True)
print("DONE", flush=True)
