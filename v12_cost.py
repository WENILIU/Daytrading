import pandas as pd, numpy as np, pickle, warnings; warnings.filterwarnings("ignore")
CAP0=4_500_000
BP1,BP2,M1,M2,MP=0.015,0.045,10.0,2.5,0.25
def run(u,bpmul=1.0,cost=0.00109):
    u=u[u["pred_q"]>=0.20]
    tr={}
    for direc in ["SHORT","LONG"]:
        s=u[u["direction"]==direc].sort_values("date")
        s["t30"]=s["p"].rolling(30,min_periods=30).mean().shift(1)
        for dt,x in zip(s["date"],s["t30"].values): tr[(dt,direc)]=x
    G={dt:sub for dt,sub in u.groupby("date")}
    ds={dt:(0.5 if (sub["direction"]=="SHORT").mean()>0.8 or (sub["direction"]=="SHORT").mean()<0.2 else 1.0) for dt,sub in G.items()}
    dc=2*(cost-0.00109)
    eq=CAP0; eqs=[CAP0]; dts=[]
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
        pn=np.asarray(sub["p"].values,dtype=float)[o]-dc; pr=np.asarray(sub["entry"].values,dtype=float)[o]
        rem=eq; W=[];R=[]
        for i in range(len(pos)):
            if pos[i]<=0: continue
            sh=float(int(pos[i]*eq/(pr[i]*1000))*1000)
            if sh<1000: continue
            if sh*pr[i]>rem:
                sh=float(int(rem/(pr[i]*1000))*1000)
                if sh<1000: continue
            rem-=sh*pr[i]; W.append(sh*pr[i]); R.append(pn[i])
        if not W: continue
        pnl=float((np.array(W)*np.array(R)).sum()/eq); eq*=1+pnl; eqs.append(eq); dts.append(dt)
    return pd.Series(eqs[1:],index=pd.to_datetime(dts))
d12=pd.read_pickle("signals_v12.pkl"); d12=d12[d12["pred"].notna()].copy(); d12["stock"]=d12["stock"].astype(str)
print("=== v12 成本敏感度（模型不變，僅調整已選交易的成本；實際重訓模型會更好）===")
print(f"成本/邊      配置        CAGR      MDD   Sharpe   2023-25    2023-26")
for cost in [0.00109,0.00140,0.00170,0.00200,0.00235,0.00300]:
    for m in [1.5,2.0]:
        e=run(d12,bpmul=m,cost=cost)
        rr=e.pct_change().fillna(0); yrs=(e.index[-1]-e.index[0]).days/365.25
        cg=(e.iloc[-1]/e.iloc[0])**(1/yrs)-1; dd=((e-e.cummax())/e.cummax()).min()
        def seg(a,b):
            s=e.loc[a:b]; yy=(s.index[-1]-s.index[0]).days/365.25
            return ((s.iloc[-1]/s.iloc[0])**(1/yy)-1)*100
        print(f"{cost*100:.3f}%   x{m:<9} {cg*100:8.1f}% {dd*100:7.2f}% {rr.mean()/rr.std()*np.sqrt(243):7.2f} {seg('2023-01-01','2025-12-31'):9.1f}% {seg('2023-01-01','2026-12-31'):9.1f}%")
print()
print("=== 容量：部位 / 當日成交額（v12 x1.5，2023 後）===")
T=pickle.load(open("v12_trades.pkl","rb"))
u=pd.read_pickle("universe15_raw.pkl"); u["stock"]=u["stock"].astype(str)
tv=u.set_index(["date","stock"])["prev_turnover"]
for k in ["v12 x1.0","v12 x1.5","v12 x3.0"]:
    ratios=[];blocked=0;tot=0
    for dt,pnl,n,expo,r,tz in T[k]:
        if pd.Timestamp(dt).year<2023: continue
        tot+=n
    # recompute per-trade notional
    print(f"  {k}: 2023 後總筆數 {tot:,}")
