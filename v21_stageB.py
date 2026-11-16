import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]:
    os.environ[k]="1"
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T
DMIN="2023-05-23"
BASE = T.D[(pd.to_datetime(T.D["date"])>=pd.Timestamp(DMIN)) & (~T.D["blocked"].values)]
def wr(trades):
    if not trades: return float("nan")
    return 100.0*sum(1 for t in trades if t[3]*t[4]>0)/len(trades)
def show(tag, th, qmin, ss, **kw):
    Dw = BASE[(BASE["pred_q"]>=qmin) & (BASE["price_dir"]<th)]
    T.GROUPS={d:g for d,g in Dw.groupby("date")}; T.days=sorted(Dw["date"].unique())
    r=T.run(slip_scale=1.0, date_min=DMIN, s3=False, size_scale=ss, exposure=1.0, capture=True, **kw)
    rets=[r["yearly"][k]/T.CAP0*100 for k in sorted(r["yearly"])]
    an=np.mean(rets); md=r["mdd"]
    flag=" <== 達標" if (an>=300 and md>=-5.0) else ("  ok<-5" if md>=-5.0 else "")
    print("%-40s MDD %+6.2f%%  年均 %+7.1f%%  cal %5.1f  勝率 %5.1f%%  筆/日 %4.1f  曝險max %5.1f%%%s" %
          (tag, md, an, abs(an/md) if md<-0.01 else 99, wr(r["trades"]), r["per_day"], r["expo_max"], flag), flush=True)
    return an,md
print("=== B1: th-1.2 q0.2 size scan ===", flush=True)
for ss in [1.2,1.4,1.6,1.8,2.0,2.3,2.6]:
    show("th-1.2 q.2 size%.1f"%ss, -0.012, 0.20, ss)
print("=== B2: th-1.0 q0.2 size scan ===", flush=True)
for ss in [1.4,1.6,1.8,2.0]:
    show("th-1.0 q.2 size%.1f"%ss, -0.010, 0.20, ss)
print("=== B3: th-1.2 q0.2 size1.8 + 單因子過濾 ===", flush=True)
for gm in [0.07,0.10]:
    show("th-1.2 size1.8 gap_max%.2f"%gm, -0.012, 0.20, 1.8, gap_max=gm)
for ml in [0.05,0.07,0.10]:
    show("th-1.2 size1.8 max_lock%.2f"%ml, -0.012, 0.20, 1.8, max_lock_rate=ml)
for zt in [0.015,0.03]:
    show("th-1.2 size1.8 zt_min%.3f"%zt, -0.012, 0.20, 1.8, zt_min_dist=zt)
print("done B", flush=True)
