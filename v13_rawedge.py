import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
from scipy import stats
s=pd.read_pickle("signals_v13.pkl"); s["stock"]=s["stock"].astype(str)
s["touch"]=np.where(s["direction"]=="SHORT",s["day_high"]>=s["lu"]-1e-9,s["day_low"]<=s["ld"]+1e-9)
s["sel"]=s["pred_q"].fillna(-1)>=0.20
def tab(sub,label):
    rows=[]
    for y,g in sub.groupby(sub["date"].dt.year):
        sh=g[g["direction"]=="SHORT"]
        rows.append((y,len(g),g["p"].mean()*100,(g["p"]>0).mean()*100,g["touch"].mean()*100,
                     len(sh),sh["p"].mean()*100 if len(sh) else np.nan))
    t=pd.DataFrame(rows,columns=["year","n","netEdge%","win%","touch%","nShort","shortEdge%"])
    t=t[t.year>=2010]
    sl=stats.linregress(t["year"].values,t["netEdge%"].values)
    e15=t[t.year.between(2015,2019)]["netEdge%"].mean(); e23=t[t.year.between(2023,2025)]["netEdge%"].mean()
    print(f"\n### {label}\n    trend={sl.slope:+.4f}pp/yr p={sl.pvalue:.4f} R2={sl.rvalue**2:.2f} | 15-19 avg={e15:.3f}% 23-25 avg={e23:.3f}% decay={(e23/e15-1)*100:+.1f}%")
    print(t.to_string(index=False,float_format=lambda v:f"{v:8.3f}"))
    return t
A=tab(s[s["abs_gap"]>=0.015],"RAW all signals 1.5%+ (no model, no sizing, net of cost)")
B=tab(s[(s["abs_gap"]>=0.015)&s["sel"]],"model-selected (pred_q>=0.20)")
C=tab(s[s["abs_gap"]>=0.05],"5%+ only (v8-style universe, raw)")
pickle.dump({"all":A,"sel":B,"g5":C},open("v13_rawedge.pkl","wb"))
