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
    return float("nan") if not trades else 100.0*sum(1 for t in trades if t[3]*t[4]>0)/len(trades)
def ev(th,qmin,ss,**kw):
    Dw=BASE[(BASE["pred_q"]>=qmin)&(BASE["price_dir"]<th)]
    T.GROUPS={d:g for d,g in Dw.groupby("date")}; T.days=sorted(Dw["date"].unique())
    r=T.run(slip_scale=1.0,date_min=DMIN,s3=False,size_scale=ss,exposure=1.0,capture=True,**kw)
    rets=[r["yearly"][k]/T.CAP0*100 for k in sorted(r["yearly"])]
    return dict(an=np.mean(rets),md=r["mdd"],win=wr(r["trades"]),per=r["per_day"],
                yrs={int(y):v for y,v in zip(sorted(r['yearly']),rets)})
rows=[]
print("=== E: 精细网格找 MDD>=-5.0 下年均最大 ===", flush=True)
for gap in [0.07,0.08,0.09]:
    for zt in [0.010,0.014,0.018]:
        for ss in [3.5,4.0,4.5,5.0,5.5]:
            d=ev(-0.012,0.20,ss,gap_max=gap,zt_min_dist=zt)
            ok = d["md"]>=-5.0
            rows.append((ok,d["an"],d["md"],d["win"],gap,zt,ss,d))
            if ok and d["an"]>=255:
                print("gap%.2f zt%.3f size%.1f  年均 %+6.1f%%  MDD %+5.2f%%  勝率%5.1f%%  per%4.1f"%(gap,zt,ss,d["an"],d["md"],d["win"],d["per"]), flush=True)
rows.sort(key=lambda x:(x[0], -x[1]))
print("\n--- 严格 MDD>=-5 下年均 TOP 8 ---", flush=True)
for ok,an,md,win,gap,zt,ss,d in rows:
    if ok:
        print("gap%.2f zt%.3f size%.1f  年均 %+6.1f%%  MDD %+5.2f%%  勝率%5.1f%% | 逐年 %s"%(
            gap,zt,ss,an,md,win," ".join("%d %+.0f"%(y,v) for y,v in d["yrs"].items())))
print("\nmax annual with MDD>=-5: %.1f%% | any 300 ok? %s"%(
    max((r[1] for r in rows if r[0]), default=0), any(r[0] and r[1]>=300 for r in rows)))
