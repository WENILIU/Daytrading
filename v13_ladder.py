import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
CAP0=4_500_000
BP1,BP2,M1,M2,MP=0.015,0.045,10.0,2.5,0.25
def run(u,bpmul=1.0):
    u=u[u["pred_q"]>=0.20]
    tr={}
    for direc in ["SHORT","LONG"]:
        s=u[u["direction"]==direc].sort_values("date")
        s["t30"]=s["p"].rolling(30,min_periods=30).mean().shift(1)
        for dt,x in zip(s["date"],s["t30"].values): tr[(dt,direc)]=x
    G={dt:sub for dt,sub in u.groupby("date")}
    ds={dt:(0.5 if (sub["direction"]=="SHORT").mean()>0.8 or (sub["direction"]=="SHORT").mean()<0.2 else 1.0) for dt,sub in G.items()}
    eq=CAP0; eqs=[CAP0]; dts=[]; rec=[]
    for dt in sorted(G):
        sub=G[dt]; peak=max(eqs); cdd=(eq-peak)/peak
        rs=0.12 if cdd<-0.012 else (0.3 if cdd<-0.006 else 1.0)
        zd=sub["zt_dist"].values
        zm=np.where(zd<BP1,M1,np.where(zd<BP2,M2,1.0))
        p=np.asarray(sub["pred"].values,dtype=float)
        kM=np.where(np.isfinite(p),np.clip(0.5+np.nan_to_num(p)/0.02,0,2),1.0)
        p30=np.array([tr.get((dt,x),np.nan) for x in sub["direction"]],dtype=float)
        kT=np.where(np.isnan(p30),1.0,np.clip(0.5+p30/0.02,0.3,2.0))
        pos=np.minimum(np.asarray(sub["base_pos"].values,dtype=float)*bpmul*zm*ds[dt]*rs*kM*kT,MP*bpmul)
        o=np.argsort(-np.nan_to_num(p,nan=-99)); pos=pos[o]
        pn=np.asarray(sub["p"].values,dtype=float)[o]; pr=np.asarray(sub["entry"].values,dtype=float)[o]
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
        eq*=1+pnl; eqs.append(eq); dts.append(dt)
        rec.append((dt,pnl,len(w),expo,r,np.array(T)))
    return pd.Series(eqs[1:],index=pd.to_datetime(dts)),rec
d=pd.read_pickle("signals_v13.pkl"); d=d[d["pred"].notna()].copy(); d["stock"]=d["stock"].astype(str)
d["touch_zt"]=np.where(d["direction"]=="SHORT",d["day_high"]>=d["lu"]-1e-9,d["day_low"]<=d["ld"]+1e-9)
print("v13 signals",len(d))
R={}
for lab,filt in [("v13 5%+ only",d["abs_gap"]>=0.05),("v13 3%+",d["abs_gap"]>=0.03),("v13 1.5%+ (全部)",d["abs_gap"]>=0.0)]:
    sub=d[filt]
    for m in [1.0,1.5]:
        e,r=run(sub,bpmul=m); R[f"{lab} x{m}"]=(e,r)
pickle.dump({k:v[0] for k,v in R.items()},open("v13_ladder_curves.pkl","wb"))
pickle.dump({k:v[1] for k,v in R.items()},open("v13_ladder_trades.pkl","wb"))
def stat(e,r,lab):
    rr=e.pct_change().fillna(0); yrs=(e.index[-1]-e.index[0]).days/365.25
    cg=(e.iloc[-1]/e.iloc[0])**(1/yrs)-1; dd=((e-e.cummax())/e.cummax()).min()
    pn=np.concatenate([x[4] for x in r]); zt=np.concatenate([x[5] for x in r])
    print(f"{lab:<20} CAGR {cg*100:7.1f}%  MDD {dd*100:6.2f}%  Shp {rr.mean()/rr.std()*np.sqrt(243):5.2f}  Calm {abs(cg/dd):5.1f}  筆 {sum(x[2] for x in r):6,} 勝 {(pn>0).mean()*100:4.1f}% 均PnL {pn.mean()*100:5.2f}% 觸板 {zt.mean()*100:4.1f}% 筆/日 {sum(x[2] for x in r)/len(r):4.1f}")
print(); print("=== 無前視階梯（同一模型、同一倉位機制，只差訊號下限）===")
for k in R: stat(*R[k],k)
print(); print("=== 區間 CAGR ===")
ks=list(R)
print(f"{'區間':<12}"+"".join(f"{k:>22}" for k in ks))
for lo,a,b in [("2015-2019","2015-01-01","2019-12-31"),("2020-2022","2020-01-01","2022-12-31"),
               ("2023-2025","2023-01-01","2025-12-31"),("2023-2026","2023-01-01","2026-12-31")]:
    cells=[]
    for k in ks:
        e=R[k][0]; s=e.loc[a:b]
        if len(s)<50: cells.append(f"{'-':>22}"); continue
        yy=(s.index[-1]-s.index[0]).days/365.25
        cells.append(f"{((s.iloc[-1]/s.iloc[0])**(1/yy)-1)*100:21.1f}%")
    print(f"{lo:<12}"+"".join(cells))
print(); print("=== 每單位曝險邊際衰減 ===")
for k in ks:
    res={}
    for lo,hi,lab in [(2015,2019,"a"),(2023,2026,"b")]:
        rows=[x for x in R[k][1] if lo<=pd.Timestamp(x[0]).year<=hi]
        if not rows: continue
        d1=np.array([x[1] for x in rows]); e1=np.array([x[3] for x in rows])
        res[lab]=(d1.mean(),e1.mean())
    if "a" in res and "b" in res:
        ea=res["a"][0]/res["a"][1]*100; eb=res["b"][0]/res["b"][1]*100
        print(f"  {k:<20} {ea:.4f}% -> {eb:.4f}%   {((eb/ea-1)*100):+6.1f}%")
