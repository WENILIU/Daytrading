import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
CAP0=4_500_000
BP1,BP2,M1,M2,MP=0.015,0.045,10.0,2.5,0.25
def run(u,bpmul=1.0):
    u=u[u["pred_q"]>=0.20] if "pred_q" in u else u
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
        pnl=float((w*r).sum()/eq); expo=float(w.sum()/eq)
        eq*=1+pnl; eqs.append(eq); dts.append(dt); rec.append((dt,pnl,len(w),expo,r))
    return pd.Series(eqs[1:],index=pd.to_datetime(dts)),rec
# ---- data ----
v8=pd.read_pickle("signals_pred_br.pkl"); v8.index=pd.read_pickle("signals_pred.pkl").index
for c in ["pred","pred_nost","pred_b"]:
    if c in v8.columns: v8=v8.drop(columns=[c])
v8=v8.rename(columns={"pred_br":"pred"}).reset_index(drop=False); v8["stock"]=v8["stock"].astype(str)
d=pd.read_pickle("signals_v11d.pkl"); d["stock"]=d["stock"].astype(str)
fl=pd.read_pickle("gap_fade_signals_filtered.pkl"); fl["stock"]=fl["stock"].astype(str)
flk={(a,b):(c,e2,f) for a,b,c,e2,f in zip(fl["date"],fl["stock"],fl["is_disposed"],fl["not_borrowable"],fl["low_turnover"])}
g=[flk.get(k) for k in zip(d["date"],d["stock"])]
d["nb_or_lt"]=[bool(x) and (x[1] or x[2]) for x in g]
d["key"]=list(zip(d["date"],d["stock"]))
s5=pd.read_pickle("gap_fade_signals_scored_filtered.pkl"); s5["stock"]=s5["stock"].astype(str)
sc=set(zip(s5["date"],s5["stock"])); d["inv8"]=[k in sc for k in d["key"]]
DP=pd.read_pickle("disposal_panel_full.pkl"); DP["stock"]=DP["stock"].astype(str)
dset=set(zip(DP["date"],DP["stock"]))
d["disposed_real"]=[k in dset for k in d["key"]]
v8["disposed_real"]=[k in dset for k in zip(v8["date"],v8["stock"])]
print("real disposal hits: v8 signals",int(v8["disposed_real"].sum()),"/",len(v8),
      f"({v8['disposed_real'].mean()*100:.2f}%)   v11 universe",int(d["disposed_real"].sum()),"/",len(d),
      f"({d['disposed_real'].mean()*100:.2f}%)")
d=d[d["pred"].notna()].copy()
B_all=d[(d["prev_turnover"]>=1e7)]
B=B_all[~B_all["disposed_real"] & ~B_all["nb_or_lt"]]
V8=v8[~v8["disposed_real"]]
print(f"v11 universe after REAL disposal+NB/LT filter: {len(B_all)} -> {len(B)} (removed {len(B_all)-len(B)}, {(len(B_all)-len(B))/len(B_all)*100:.2f}%)")
print(f"v8 after REAL disposal: {len(v8)} -> {len(V8)}")
R={}
e,r=run(V8.assign(pred_q=0.5) if "pred_q" not in V8 else V8); R["v8_real"]=(e,r)
for m in [1.5,2.0,3.0]: R["v11 x%.1f"%m]=(run(B,bpmul=m))
pickle.dump({k:v[0] for k,v in R.items()},open("final_curves_realdisp.pkl","wb"))
pickle.dump({k:v[1] for k,v in R.items()},open("final_trades_realdisp.pkl","wb"))
def stat(e,r,lab):
    rr=e.pct_change().fillna(0); yrs=(e.index[-1]-e.index[0]).days/365.25
    cg=(e.iloc[-1]/e.iloc[0])**(1/yrs)-1; dd=((e-e.cummax())/e.cummax()).min()
    n=sum(x[2] for x in r)
    pn=np.concatenate([x[4] for x in r])
    print(f"{lab:<14} CAGR {cg*100:7.1f}%  MDD {dd*100:6.2f}%  Sharpe {rr.mean()/rr.std()*np.sqrt(243):5.2f}  Calmar {abs(cg/dd):5.1f}  筆 {n:6,}  勝率 {(pn>0).mean()*100:4.1f}%")
print()
print("=== 用真實處置名單（取代代理）===")
for k in R: stat(*R[k],k)
print()
print("=== 區間 CAGR（真實日數）===")
ks=list(R)
print(f"{'區間':<14}"+"".join(f"{k:>16}" for k in ks))
for lo,a,b in [("2010-2014","2010-01-01","2014-12-31"),("2015-2019","2015-01-01","2019-12-31"),
               ("2020-2022","2020-01-01","2022-12-31"),("2023-2025","2023-01-01","2025-12-31"),
               ("2023-2026","2023-01-01","2026-12-31")]:
    cells=[]
    for k in ks:
        e=R[k][0]; s=e.loc[a:b]
        if len(s)<50: cells.append(f"{'-':>16}"); continue
        yy=(s.index[-1]-s.index[0]).days/365.25
        cells.append(f"{((s.iloc[-1]/s.iloc[0])**(1/yy)-1)*100:15.1f}%")
    print(f"{lo:<14}"+"".join(cells))
