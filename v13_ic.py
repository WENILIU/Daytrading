import pandas as pd, numpy as np, warnings; warnings.filterwarnings("ignore")
from scipy import stats
s=pd.read_pickle("signals_v13.pkl"); s["stock"]=s["stock"].astype(str)
s=s[s["pred"].notna()].copy()
s["sel"]=s["pred_q"].fillna(-1)>=0.20
rows=[]
for y,g in s.groupby(s["date"].dt.year):
    if y<2014: continue
    sh=g[g["direction"]=="SHORT"]
    ic=stats.spearmanr(sh["pred"],sh["p"]).statistic if len(sh)>50 else np.nan
    top=sh.nlargest(max(1,int(len(sh)*0.2)),"pred")["p"].mean()*100
    bot=sh.nsmallest(max(1,int(len(sh)*0.2)),"pred")["p"].mean()*100
    g5=sh[sh["abs_gap"]>=0.05]
    ic5=stats.spearmanr(g5["pred"],g5["p"]).statistic if len(g5)>50 else np.nan
    rows.append((y,len(sh),ic,ic5,top*100/100,bot,top-bot))
t=pd.DataFrame(rows,columns=["year","nShort","IC_all","IC_5%+","top20%edge%","bot20%edge%","spread%"])
sl=stats.linregress(t["year"].values,t["IC_all"].values)
print("model OOS IC by year (SHORT only)")
print(t.to_string(index=False,float_format=lambda v:f"{v:8.4f}"))
print(f"\nIC trend={sl.slope:+.4f}/yr p={sl.pvalue:.4f}")
e15=t[t.year.between(2015,2019)]["IC_all"].mean(); e23=t[t.year.between(2023,2025)]["IC_all"].mean()
s15=t[t.year.between(2015,2019)]["spread%"].mean(); s23=t[t.year.between(2023,2025)]["spread%"].mean()
print(f"IC 15-19={e15:.4f} 23-25={e23:.4f}  spread 15-19={s15:.3f}% 23-25={s23:.3f}%")
