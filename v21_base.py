import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]:
    os.environ[k]="1"
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

DMIN="2023-05-23"
print("D columns:", list(T.D.columns))
BASE = T.D[(pd.to_datetime(T.D["date"])>=pd.Timestamp(DMIN)) & (~T.D["blocked"].values)]
print("BASE rows (2023-05+, ~blocked):", len(BASE))
print("pred_q notna:", int(BASE["pred_q"].notna().sum()), " price_dir notna:", int(BASE["price_dir"].notna().sum()))
print("pred_q quantiles:", np.round(np.nanpercentile(BASE["pred_q"].dropna(),[10,25,50,75,90]),3).tolist())

def wr(trades):
    if not trades: return float("nan")
    w=sum(1 for t in trades if t[3]*t[4]>0)
    return 100.0*w/len(trades)

def show(tag, th, qmin, ss, dir_cap=None, max_lock_rate=None, zt_min_dist=None,
         gap_max=None, brake=((-0.03,0.30),(-0.06,0.12)), capture=True):
    Dw = BASE[(BASE["pred_q"]>=qmin) & (BASE["price_dir"]<th)]
    T.GROUPS={d:g for d,g in Dw.groupby("date")}; T.days=sorted(Dw["date"].unique())
    r=T.run(slip_scale=1.0, date_min=DMIN, s3=False, size_scale=ss, exposure=1.0,
            dir_cap=dir_cap, max_lock_rate=max_lock_rate, zt_min_dist=zt_min_dist,
            gap_max=gap_max, brake=brake, capture=capture)
    yrs=sorted(r["yearly"]); rets=[r["yearly"][k]/T.CAP0*100 for k in yrs]
    w = wr(r["trades"]) if capture else float("nan")
    print("%-40s MDD %+6.2f%%  年均 %+7.1f%%  勝率 %5.1f%%  筆/日 %4.1f  曝險max %5.1f%%  筆數 %d" %
          (tag, r["mdd"], np.mean(rets), w, r["per_day"], r["expo_max"], len(r["trades"])))
    return r, np.mean(rets), r["mdd"], w

print()
print("=== 基線確認（應接近 年均+199.1 MDD-4.29）===")
show("th-0.8 q0.2 std size1.4 (穩健)", -0.008, 0.20, 1.4)
