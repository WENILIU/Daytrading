import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
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
    eq=CAP0; eqs=[CAP0]; dts=[]; expo=[]
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
        w=np.array(W); r=np.array(R)
        pnl=float((w*r).sum()/eq); expo.append(float(w.sum()/eq))
        eq*=1+pnl; eqs.append(eq); dts.append(dt)
    return pd.Series(eqs[1:],index=pd.to_datetime(dts)),np.array(expo)
d=pd.read_pickle("signals_v13.pkl"); d=d[d["pred"].notna()].copy(); d["stock"]=d["stock"].astype(str)
COSTS=[0.00109,0.00159,0.00209,0.00259,0.00309,0.00409]
rows=[]
for lab,filt in [("5%+",d["abs_gap"]>=0.05),("3%+",d["abs_gap"]>=0.03),("1.5%+",d["abs_gap"]>=0.0)]:
    for m in [1.0,1.5]:
        sub=d[filt]
        for c in COSTS:
            e,xp=run(sub,bpmul=m,cost=c)
            rr=e.pct_change().fillna(0); yrs=(e.index[-1]-e.index[0]).days/365.25
            cg=(e.iloc[-1]/e.iloc[0])**(1/yrs)-1; dd=((e-e.cummax())/e.cummax()).min()
            s=e.loc["2023-01-01":"2025-12-31"]; yy=(s.index[-1]-s.index[0]).days/365.25
            rc=(s.iloc[-1]/s.iloc[0])**(1/yy)-1
            rows.append({"floor":lab,"bpm":m,"cost":c,"cagr":cg,"mdd":dd,"sharpe":rr.mean()/rr.std()*np.sqrt(243),"recent":rc,"expo":xp.mean()})
        print("done",lab,m,flush=True)
df=pd.DataFrame(rows); df.to_csv("v13_robust.csv",index=False,encoding="utf-8-sig")
print()
print("=== 滑價穩健度（成本/邊；0.109%=現行無滑價，0.159%=+0.05%滑價，0.209%=+0.10%...）===")
print(f"{'下限':<7}{'倍':>4}"+"".join(f"{c*100:>9.3f}%" for c in COSTS)+"   近年@+0.10%滑價")
for (lab,m),g in df.groupby(["floor","bpm"],sort=False):
    g=g.set_index("cost")
    line=f"{lab:<7}{m:>4.1f}"
    for c in COSTS:
        line+=f"{g.loc[c,'cagr']*100:9.1f}"
    line+=f"     {g.loc[0.00209,'recent']*100:8.1f}%"
    print(line)
print()
print("=== 各設定的「CAGR 跌破 50% 的成本容忍度」===")
for (lab,m),g in df.groupby(["floor","bpm"],sort=False):
    g=g.set_index("cost")
    be=None
    for c in np.arange(0.00109,0.0101,0.00010):
        pass
    # interpolate where cagr crosses 0.5
    cs=g["cagr"].values*100; xs=np.array(g.index)*100
    if cs[-1]>50: print(f"  {lab} x{m}: 在 {xs[-1]:.3f}%/邊 仍有 {cs[-1]:.1f}% -> 容忍度 >{xs[-1]:.3f}%"); continue
    for i in range(len(cs)-1):
        if cs[i]>=50>cs[i+1]:
            f=(cs[i]-50)/(cs[i]-cs[i+1]); be=xs[i]+f*(xs[i+1]-xs[i]); break
    print(f"  {lab} x{m}: 成本容忍度 = {be:.3f}%/邊（即額外滑價 {be-0.109:.3f}%/邊）")
