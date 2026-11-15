import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T
DMIN="2023-05-23"
BASE = T.D[(pd.to_datetime(T.D["date"]) >= pd.Timestamp(DMIN)) & (~T.D["blocked"].values)]
def show(tag, th, qmin, brake, ss):
    Dw = BASE[(BASE["pred_q"]>=qmin) & (BASE["price_dir"]<th)]
    T.GROUPS={d:g for d,g in Dw.groupby("date")}; T.days=sorted(Dw["date"].unique())
    r=T.run(slip_scale=1.0, date_min=DMIN, s3=False, size_scale=ss, exposure=1.0, brake=brake)
    yrs=sorted(r["yearly"]); rets=[r["yearly"][k]/T.CAP0*100 for k in yrs]
    daily=pd.DataFrame(r["daily"],columns=["date","yuan","book","dd"]); daily["year"]=pd.to_datetime(daily["date"]).dt.year
    print("\n[%s] th=%.1f%% q>=%.1f brake=%s size=%.1f" % (tag, th*100, qmin, brake_key, ss))
    print("  年均 %+.1f%%  部位MDD %+.2f%%  筆/日 %.1f  曝險max %.0f%% (<=100%% 不需借錢)" %
          (np.mean(rets), r["mdd"], r["per_day"], r["expo_max"]))
    for y in yrs:
        sub=daily[daily["year"]==y]
        print("    %d: 報酬 %+.0f%%  年內最差回撤 %+.2f%%" % (y, rets[yrs.index(y)], sub["dd"].min()*100))
STD=((-0.03,0.30),(-0.06,0.12))
brake_key="std"; show("激進-達標200", -0.008, 0.20, STD, 1.6)
show("穩健-高calmar", -0.008, 0.20, STD, 1.4)
show("現行對照(-0.5)", -0.005, 0.20, STD, 1.0)
