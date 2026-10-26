import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
CAP0=4_500_000
BP1,BP2,M1,M2,MP=0.015,0.045,10.0,2.5,0.25

def run(u,bpmul=1.0,use_ds=True,cost=0.00109):
    u=u[u["pred_q"]>=0.20]
    tr={}
    for direc in ["SHORT","LONG"]:
        s=u[u["direction"]==direc].sort_values("date")
        if len(s)==0: continue
        s["t30"]=s["p"].rolling(30,min_periods=30).mean().shift(1)
        for dt,x in zip(s["date"],s["t30"].values): tr[(dt,direc)]=x
    G={dt:sub for dt,sub in u.groupby("date")}
    dsf={dt:(0.5 if (sub["direction"]=="SHORT").mean()>0.8 or (sub["direction"]=="SHORT").mean()<0.2 else 1.0) for dt,sub in G.items()}
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
        dv=0.5 if (use_ds and dsf[dt]<1) else 1.0
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

d=pd.read_pickle("signals_v13.pkl"); d=d[d["pred"].notna()].copy(); d["stock"]=d["stock"].astype(str)
d["touch_zt"]=np.where(d["direction"]=="SHORT",d["day_high"]>=d["lu"]-1e-9,d["day_low"]<=d["ld"]+1e-9)

CFG={}
CFG["v8 (5%+, real disposal)"]=pickle.load(open("final_trades_realdisp.pkl","rb"))["v8_real"]
for lab,sub,uds,m in [("v13 1.5%+ ds=ON x1.0",d,True,1.0),("v13 1.5%+ ds=ON x1.5",d,True,1.5),
                      ("v13 1.5%+ ds=OFF x1.0",d,False,1.0),("v13 1.5%+ ds=OFF x1.5",d,False,1.5),
                      ("v13 3%+ ds=ON x1.5",d[d["abs_gap"]>=0.03],True,1.5)]:
    CFG[lab]=run(sub,bpmul=m,use_ds=uds)

def yr_tab(rec):
    df=pd.DataFrame([(x[0],x[1],x[2],x[3]) for x in rec],columns=["date","pnl","n","expo"])
    has=any(len(x)>5 for x in rec)
    dates=np.concatenate([[x[0]]*len(x[4]) for x in rec])
    pv=np.concatenate([x[4] for x in rec])
    if has:
        zv=np.concatenate([np.asarray(x[5],dtype=float) if len(x)>5 else np.full(len(x[4]),np.nan) for x in rec])
    else:
        zv=np.full(len(pv),np.nan)
    tdf=pd.DataFrame({"date":dates,"p":pv,"zt":zv})
    rows=[]
    for y,g in df.groupby(df["date"].dt.year):
        t=tdf[tdf["date"].dt.year==y]
        rows.append((y,(np.prod(1+g["pnl"].values)-1)*100, g["pnl"].sum()/g["expo"].sum()*100,
                     (t["p"]>0).mean()*100, t["p"].mean()*100,
                     (t["zt"].mean()*100 if has else np.nan), g["n"].mean(), g["expo"].mean()*100))
    return pd.DataFrame(rows,columns=["year","ret%","edgePerExpo%","win%","avgPnL%","touchZT%","nPerDay","expo%"])

out={}
for lab,rec in CFG.items():
    t=yr_tab(rec); out[lab]=t
    e5=t[t.year.between(2015,2019)]["edgePerExpo%"].mean(); e23=t[t.year.between(2023,2025)]["edgePerExpo%"].mean()
    r5=t[t.year.between(2015,2019)]["ret%"].mean(); r23=t[t.year.between(2023,2025)]["ret%"].mean()
    print("")
    print(f"### {lab}  |  edge/expo 15-19={e5:.3f}% 23-25={e23:.3f}% decay={(e23/e5-1)*100:+.1f}%  |  avg annual 15-19={r5:.0f}% 23-25={r23:.0f}% ratio={r23/r5*100:.0f}%")
    print(t.to_string(index=False,float_format=lambda v:f"{v:8.2f}"))
pickle.dump(out,open("v13_decay_tables.pkl","wb"))
with open("v13_decay.txt","w",encoding="utf-8") as f:
    for lab,t in out.items():
        f.write(f"\n=== {lab} ===\n"+t.to_string(index=False,float_format=lambda v:f"{v:8.2f}")+"\n")
