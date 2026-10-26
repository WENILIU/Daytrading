import pandas as pd, numpy as np, warnings; warnings.filterwarnings("ignore")
s=pd.read_pickle("signals_v13.pkl"); s["stock"]=s["stock"].astype(str)
s["touch"]=np.where(s["direction"]=="SHORT",s["day_high"]>=s["lu"]-1e-9,s["day_low"]<=s["ld"]+1e-9)
s["sel"]=s["pred_q"].fillna(-1)>=0.20
s=s[s["direction"]=="SHORT"]
bins=[0,0.015,0.03,0.05,0.08,0.12,1.0]
lab=["<1.5%","1.5-3%","3-5%","5-8%","8-12%",">12%"]
s["zb"]=pd.cut(s["zt_dist"],bins,labels=lab)
s["era"]=pd.cut(s["date"].dt.year,[2009,2019,2022,2026],labels=["2010-2019","2020-2022","2023-2026"])
for tag,sub in [("RAW 1.5%+",s[s["abs_gap"]>=0.015]),("SELECTED 1.5%+",s[(s["abs_gap"]>=0.015)&s["sel"]]),("RAW 5%+",s[s["abs_gap"]>=0.05])]:
    print(f"\n===== {tag} : 每筆淨邊際 by zt_dist bucket x era =====")
    p=sub.pivot_table(index="zb",columns="era",values="p",aggfunc=lambda x:np.mean(x)*100,observed=True)
    n=sub.pivot_table(index="zb",columns="era",values="p",aggfunc="size",observed=True)
    t=sub.pivot_table(index="zb",columns="era",values="touch",aggfunc="mean",observed=True)*100
    out=pd.concat({"edge%":p,"n":n,"touch%":t},axis=1)
    print(out.to_string(float_format=lambda v:f"{v:9.1f}"))
