import pandas as pd, numpy as np, pickle, warnings; warnings.filterwarnings("ignore")
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
    eq=CAP0; eqs=[CAP0]; out=[]
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
        pr=np.asarray(sub["entry"].values,dtype=float)[o]
        ptv=np.asarray(sub["prev_turnover"].values,dtype=float)[o]
        ag=np.asarray(sub["abs_gap"].values,dtype=float)[o]
        rem=eq; rec=[]; blocked=0
        for i in range(len(pos)):
            if pos[i]<=0: continue
            sh=float(int(pos[i]*eq/(pr[i]*1000))*1000)
            if sh<1000: blocked+=1; continue
            if sh*pr[i]>rem:
                sh=float(int(rem/(pr[i]*1000))*1000)
                if sh<1000: blocked+=1; continue
            rem-=sh*pr[i]; rec.append((sh*pr[i],ptv[i],ag[i]))
        if not rec: continue
        eq*=1+0.0; eqs.append(eq)
        for notional,tv0,a in rec:
            out.append((dt,notional,tv0,notional/max(tv0,1),a))
    return pd.DataFrame(out,columns=["date","notional","prev_turnover","ratio","abs_gap"]),blocked
d12=pd.read_pickle("signals_v12.pkl"); d12=d12[d12["pred"].notna()].copy(); d12["stock"]=d12["stock"].astype(str)
print("=== 容量測試（固定 450 萬、2023-01 之後、整張）===")
for m in [1.0,1.5,2.0,3.0]:
    df,blocked=run(d12,bpmul=m)
    df=df[pd.to_datetime(df["date"])>=pd.Timestamp("2023-01-01")]
    r=df["ratio"].values
    print(f"  x{m}: 可成交 {len(df):6,} 筆  被整張卡掉 {blocked:5,}  部位/昨日成交額  中位 {np.median(r)*100:.2f}%  P90 {np.percentile(r,90)*100:.1f}%  P99 {np.percentile(r,99)*100:.1f}%  max {r.max()*100:.1f}%  >5%佔比 {(r>0.05).mean()*100:.2f}%")
    print(f"        單筆名義 中位 {np.median(df['notional']):,.0f} 元  最大 {df['notional'].max():,.0f} 元   gap帶分佈: 1.5-3% {np.mean(df['abs_gap']<0.03)*100:.0f}%  3-5% {np.mean((df['abs_gap']>=0.03)&(df['abs_gap']<0.05))*100:.0f}%  5%+ {np.mean(df['abs_gap']>=0.05)*100:.0f}%")
