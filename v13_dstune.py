import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
from scipy import stats
CAP0=4_500_000
BP1,BP2,M1,M2,MP=0.015,0.045,10.0,2.5,0.25

def run(u,bpmul=1.0,dsfac=1.0,cost=0.00109):
    u=u[u["pred_q"]>=0.20]
    tr={}
    for direc in ["SHORT","LONG"]:
        s=u[u["direction"]==direc].sort_values("date")
        if len(s)==0: continue
        s["t30"]=s["p"].rolling(30,min_periods=30).mean().shift(1)
        for dt,x in zip(s["date"],s["t30"].values): tr[(dt,direc)]=x
    G={dt:sub for dt,sub in u.groupby("date")}
    dsf={dt:(dsfac if (sub["direction"]=="SHORT").mean()>0.8 or (sub["direction"]=="SHORT").mean()<0.2 else 1.0) for dt,sub in G.items()}
    dc=2*(cost-0.00109)
    eq=CAP0; peak=CAP0; rec=[]
    for dt in sorted(G):
        sub=G[dt]
        cdd=(eq-peak)/peak
        rs=0.12 if cdd<-0.012 else (0.3 if cdd<-0.006 else 1.0)
        zd=sub["zt_dist"].values
        zm=np.where(zd<BP1,M1,np.where(zd<BP2,M2,1.0))
        p=np.asarray(sub["pred"].values,dtype=float)
        kM=np.where(np.isfinite(p),np.clip(0.5+np.nan_to_num(p)/0.02,0,2),1.0)
        p30=np.array([tr.get((dt,x),np.nan) for x in sub["direction"]],dtype=float)
        kT=np.where(np.isnan(p30),1.0,np.clip(0.5+p30/0.02,0.3,2.0))
        dv=dsf[dt]
        pos=np.minimum(np.asarray(sub["base_pos"].values,dtype=float)*bpmul*zm*dv*rs*kM*kT,MP*bpmul)
        o=np.argsort(-np.nan_to_num(p,nan=-99)); pos=pos[o]
        pn=np.asarray(sub["p"].values,dtype=float)[o]-dc; pr=np.asarray(sub["entry"].values,dtype=float)[o]
        tz=sub["touch_zt"].values.astype(float)[o]
        rem=eq; W=[];R=[];T=[]
        for i in range(len(pos)):
            if pos[i]<=0: continue
            sh=float(int(pos[i]*eq/(pr[i]*1000))*1000)
            if sh<1000: continue
            if sh*pr[i]>rem:
                sh=float(int(rem/(pr[i]*1000))*1000)
                if sh<1000: continue
            rem-=sh*pr[i]; W.append(sh*pr[i]); R.append(pn[i]); T.append(tz[i])
        if not W: continue
        w=np.array(W); r=np.array(R)
        pnl=float((w*r).sum()/eq); expo=float(w.sum()/eq)
        eq*=1+pnl; peak=max(peak,eq)
        rec.append((dt,pnl,len(w),expo,r,np.array(T)))
    return rec

def perf(rec):
    e=pd.Series([1+ x[1] for x in rec],index=[x[0] for x in rec]).cumprod()
    rr=e.pct_change().fillna(0); yrs=(e.index[-1]-e.index[0]).days/365.25
    cg=(e.iloc[-1]/e.iloc[0])**(1/yrs)-1; dd=((e-e.cummax())/e.cummax()).min()
    sh=rr.mean()/rr.std()*np.sqrt(243)
    def seg(a,b):
        s=e.loc[a:b]; yy=(s.index[-1]-s.index[0]).days/365.25
        return ((s.iloc[-1]/s.iloc[0])**(1/yy)-1)*100
    d=pd.DataFrame([(x[0],x[1],x[2],x[3]) for x in rec],columns=["date","pnl","n","expo"])
    ye=d.groupby(d["date"].dt.year).apply(lambda g:g["pnl"].sum()/g["expo"].sum(),include_groups=False)
    yrs_idx=np.array(ye.index,dtype=float); yv=ye.values
    sl=stats.linregress(yrs_idx,yv)
    m15=yv[(ye.index>=2015)&(ye.index<=2019)].mean(); m23=yv[(ye.index>=2023)&(ye.index<=2025)].mean()
    return dict(cagr=cg*100,mdd=dd*100,sharpe=sh,calm=abs(cg/dd),seg23=seg("2023-01-01","2025-12-31"),
                slope=sl.slope*100,pval=sl.pvalue,e15=m15,e23=m23,decay=(m23/m15-1)*100,
                expo=np.mean([x[3] for x in rec])*100,maxexpo=max(x[3] for x in rec)*100,
                nperday=np.mean([x[2] for x in rec]))

d=pd.read_pickle("signals_v13.pkl"); d=d[d["pred"].notna()].copy(); d["stock"]=d["stock"].astype(str)
d["touch_zt"]=np.where(d["direction"]=="SHORT",d["day_high"]>=d["lu"]-1e-9,d["day_low"]<=d["ld"]+1e-9)
G={dt:sub for dt,sub in d.groupby("date")}
fire=np.mean([1.0 if ((sub["direction"]=="SHORT").mean()>0.8 or (sub["direction"]=="SHORT").mean()<0.2) else 0.0 for sub in G.values()])
gy=pd.Series([(sub["direction"]=="SHORT").mean() for sub in G.values()],index=list(G)).groupby(lambda x:x.year).mean()
print(f"ds 觸發率（全期）= {fire*100:.1f}%   逐年 SHORT 佔比:")
print((gy*100).round(1).to_string())
print("")
rows=[]
for m in [1.0,1.5,2.0]:
    for f in [1.0,0.85,0.7,0.5]:
        r=perf(run(d,bpmul=m,dsfac=f)); r["mul"]=m; r["dsfac"]=f; rows.append(r)
t=pd.DataFrame(rows)[["mul","dsfac","cagr","mdd","sharpe","calm","seg23","decay","slope","pval","e15","e23","expo","maxexpo","nperday"]]
print(t.to_string(index=False,float_format=lambda v:f"{v:9.3f}"))
t.to_csv("v13_dstune.csv",index=False,encoding="utf-8-sig")
