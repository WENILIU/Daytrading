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
    print("%-34s MDD %+6.2f%%  年均 %+7.1f%%  勝率 %5.1f%%  筆/日 %4.1f  曝險max %5.1f%%  筆數 %5d" %
          (tag, r["mdd"], np.mean(rets), wr(r["trades"]), r["per_day"], r["expo_max"], len(r["trades"])), flush=True)
    return np.mean(rets), r["mdd"]
print("=== Stage A: 品質軸 (s3 th x pred_q), size=1.4, std brake ===", flush=True)
for th in [-0.008,-0.012,-0.015]:
    for q in [0.20,0.35,0.50,0.65]:
        show("th%.1f%% q%.2f" % (th*100,q), th, q, 1.4)
print("done A", flush=True)
