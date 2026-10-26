import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
CAPITAL=4_500_000; COST=0.00109
d=pd.read_pickle("signals_v11c.pkl")
d["touch_zt"]=np.where(d["direction"]=="SHORT",d["day_high"]>=d["lu"]-1e-9,d["day_low"]<=d["ld"]+1e-9)
BP1,BP2,M1,M2,MP=0.015,0.045,10.0,2.5,0.25
def build(gap_s,gap_l,skip_q):
    m=((d["direction"]=="SHORT")&(d["abs_gap"]>=gap_s))|((d["direction"]=="LONG")&(d["abs_gap"]>=gap_l))
    u=d[m].copy()
    u=u[u["pred_q"]>=skip_q]
    u=u[u["pred"].notna()]
    tr={}
    for direc in ["SHORT","LONG"]:
        s=u[u["direction"]==direc].sort_values("date")
        s["t30"]=s["p"].rolling(30,min_periods=30).mean().shift(1)
        for dt,x in zip(s["date"],s["t30"].values): tr[(dt,direc)]=x
    G={dt:sub for dt,sub in u.groupby("date")}
    dates=sorted(G)
    ds={}
    for dt in dates:
        sub=G[dt]; sp=(sub["direction"]=="SHORT").mean()
        ds[dt]=0.5 if sp>0.8 or sp<0.2 else 1.0
    D={}
    for dt in dates:
        sub=G[dt]
        D[dt]={"bp":sub["base_pos"].values,"zt_d":sub["zt_dist"].values,"dirs":sub["direction"].values,
               "pnls":sub["p"].values,"pr":sub["pred"].values,
               "t30":np.array([tr.get((dt,x),np.nan) for x in sub["direction"]],dtype=float),
               "zt":sub["touch_zt"].values,"gap":sub["abs_gap"].values}
    return D,dates,ds
def run(D,dates,ds):
    cap=CAPITAL; eq=[CAPITAL]; tr=[]
    for dt in dates:
        dd=D[dt]; peak=max(eq); cdd=(cap-peak)/peak
        rs=0.12 if cdd<-0.012 else (0.3 if cdd<-0.006 else 1.0)
        zm=np.where(dd["zt_d"]<BP1,M1,np.where(dd["zt_d"]<BP2,M2,1.0))
        p=dd["pr"]; kM=np.where(np.isfinite(p),np.clip(0.5+np.nan_to_num(p)/0.02,0,2),1.0)
        t=dd["t30"]; kT=np.where(np.isnan(t),1.0,np.clip(0.5+t/0.02,0.3,2.0))
        pos=dd["bp"]*zm*ds[dt]*rs*kM*kT
        pos=np.minimum(pos,MP); pos=np.minimum(pos,1.0)
        o=np.argsort(-np.nan_to_num(p,nan=-99))
        pos=pos[o]; pn=dd["pnls"][o]; zt=dd["zt"][o]; gp=dd["gap"][o]
        cum=np.cumsum(pos); mask=cum<=1.0
        if (~mask).any():
            fo=np.argmax(~mask); rem=1.0-(cum[fo-1] if fo>0 else 0.0); pos[fo]=max(0,rem); pos[fo+1:]=0
        cap*=1+float((pos*pn).sum()); eq.append(cap)
        tr.append((dt,float((pos*pn).sum()),int((pos>0).sum()),float(pos.sum()),
                   int(np.sum((pn>0)&(pos>0))),float(np.mean(pn[pos>0])) if (pos>0).any() else 0.0,
                   float(np.mean(zt[pos>0])) if (pos>0).any() else 0.0,
                   float(np.mean(gp[pos>0])) if (pos>0).any() else 0.0))
    return eq,tr
def stats(eq,tr,label,store=None):
    e=pd.Series(eq[1:],index=pd.to_datetime([t[0] for t in tr]))
    r=e.pct_change().fillna(0); yrs=(e.index[-1]-e.index[0]).days/365.25
    cg=(e.iloc[-1]/e.iloc[0])**(1/yrs)-1; dd=((e-e.cummax())/e.cummax()).min()
    sh=r.mean()/r.std()*np.sqrt(243)
    def w(a,b):
        s=e.loc[a:b]; yy=(s.index[-1]-s.index[0]).days/365.25
        return (s.iloc[-1]/s.iloc[0])**(1/yy)-1
    ntr=sum(t[2] for t in tr); win=sum(t[4] for t in tr)/max(ntr,1)
    print(f"{label:<26} CAGR {cg*100:7.1f}%  MDD {dd*100:6.2f}%  Sharpe {sh:5.2f}  筆數{ntr:7d} 勝率{win*100:4.1f}%  曝險{np.mean([t[3] for t in tr])*100:5.1f}%  | 23-25 {w('2023-01-01','2025-12-31')*100:6.1f}%  24-25 {w('2024-01-01','2025-12-31')*100:6.1f}%  16-19 {w('2016-01-01','2019-12-31')*100:6.1f}%")
    if store is not None: store[label]=(e,tr)
CFG=[("v11c @5% only (skip20%)",0.05,0.05,0.20),
     ("v11c SHORT3% LONG5%",0.03,0.05,0.20),
     ("v11c both 3%",0.03,0.03,0.20),
     ("v11c SHORT3% LONG5% skip30",0.03,0.05,0.30),
     ("v11c SHORT4% LONG5%",0.04,0.05,0.20)]
st={}
for nm,gs,gl,sq in CFG:
    D,dates,ds=build(gs,gl,sq); eq,tr=run(D,dates,ds); stats(eq,tr,nm,st)
pickle.dump(st,open("v11_runs.pkl","wb"))
