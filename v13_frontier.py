import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
from scipy import stats
exec(open("v13_dstune.py",encoding="utf-8").read().split("d=pd.read_pickle")[0])
d=pd.read_pickle("signals_v13.pkl"); d=d[d["pred"].notna()].copy(); d["stock"]=d["stock"].astype(str)
d["touch_zt"]=np.where(d["direction"]=="SHORT",d["day_high"]>=d["lu"]-1e-9,d["day_low"]<=d["ld"]+1e-9)
rows=[]
for m in [0.5,0.6,0.7,0.8,0.85,1.0,1.2,1.5,2.0]:
    r=perf(run(d,bpmul=m,dsfac=1.0)); r["mul"]=m; rows.append(r)
t=pd.DataFrame(rows)[["mul","cagr","mdd","sharpe","calm","seg23","decay","slope","pval","expo","maxexpo","nperday"]]
print("=== clean leverage frontier (ds removed) ===")
print(t.to_string(index=False,float_format=lambda v:f"{v:9.3f}"))
t.to_csv("v13_frontier.csv",index=False,encoding="utf-8-sig")
