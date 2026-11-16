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
    flag="  <== 達標300" if (an>=300 and md>=-5.0) else ""
    print("%-46s MDD %+6.2f%%  年均 %+7.1f%%  cal %5.1f  勝率 %5.1f%%  筆/日 %4.1f | 逐年 %s%s" %
          (tag, md, an, abs(an/md) if md<-0.01 else 99, wr(r["trades"]), r["per_day"],
           " ".join("%d %+.0f"%(y,v) for y,v in zip(sorted(r['yearly']),rets)), flag), flush=True)
    return an,md
print("=== D1: th-1.5 gap.07 zt.015, size scan ===", flush=True)
for ss in [2.6,3.5,4.5,5.5,6.5]:
    show("th-1.5 gap.07 zt.015 size%.1f"%ss, -0.015,0.20,ss, gap_max=0.07, zt_min_dist=0.015)
print("=== D2: th-1.2 gap.07 zt.015 + dir_cap, size scan ===", flush=True)
for ss in [4,5,6,7]:
    show("dir_cap.5 size%.1f"%ss, -0.012,0.20,ss, gap_max=0.07, zt_min_dist=0.015, dir_cap=0.5)
    show("dir_cap.6 size%.1f"%ss, -0.012,0.20,ss, gap_max=0.07, zt_min_dist=0.015, dir_cap=0.6)
print("=== D3: 細調 th/gap @ size4.5 ===", flush=True)
show("th-1.0 gap.07 zt.015 size4.5", -0.010,0.20,4.5, gap_max=0.07, zt_min_dist=0.015)
show("th-1.2 gap.06 zt.015 size5.0", -0.012,0.20,5.0, gap_max=0.06, zt_min_dist=0.015)
show("th-1.2 gap.08 zt.012 size4.5", -0.012,0.20,4.5, gap_max=0.08, zt_min_dist=0.012)
print("done D", flush=True)
