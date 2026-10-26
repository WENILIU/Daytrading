import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
exec(open("fast_nm.py").read().split("print(\"=\"*60)")[0])
df=pd.read_pickle("signals_pred_br.pkl"); df.index=pd.read_pickle("signals_pred.pkl").index
raw=np.where(df["score"].values>=3,calc_pnl_vec(df,0.20,0.04),calc_pnl_vec(df,0.12,0.04))
df["raw"]=raw
is_s=df["direction"]=="SHORT"
df["touch_zt"]=np.where(is_s,df["day_high"]>=df["lu"]-1e-9,df["day_low"]<=df["ld"]+1e-9)
df["year"]=pd.to_datetime(df["date"]).dt.year
BP1,BP2,M1,M2,MP=0.015,0.045,10.0,2.5,0.25
def build(cost):
    d2=df.copy(); d2["p"]=d2["raw"]-2*cost
    trail={}
    for direc in ["SHORT","LONG"]:
        s=d2[d2["direction"]==direc].sort_values("date")
        s["t30"]=s["p"].rolling(30,min_periods=30).mean().shift(1)
        for dt,x in zip(s["date"],s["t30"].values): trail[(dt,direc)]=x
    D={}
    for d in dates:
        if d not in g: continue
        sub=g[d]; ix=sub.index.values
        D[d]={"bp":d2.loc[ix,"base_pos"].values,"zt_d":d2.loc[ix,"zt_dist"].values,
          "dirs":d2.loc[ix,"direction"].values,"pnls":d2.loc[ix,"p"].values,
          "pr":np.asarray(d2.loc[ix,"pred_br"].values,dtype=float),
          "t30":np.array([trail.get((d,x),np.nan) for x in d2.loc[ix,"direction"]],dtype=float)}
    return D
def run(D):
    capital=CAPITAL; eq=[CAPITAL]; tr=[]
    for d in dates:
        if d not in D: eq.append(capital); continue
        dd=D[d]; peak=max(eq); cdd=(capital-peak)/peak
        rs=0.12 if cdd<-0.012 else (0.3 if cdd<-0.006 else 1.0)
        zm=np.where(dd["zt_d"]<BP1,M1,np.where(dd["zt_d"]<BP2,M2,1.0))
        p=dd["pr"]; kM=np.where(np.isfinite(p),np.clip(0.5+np.nan_to_num(p)/0.02,0,2),1.0)
        t=dd["t30"]; kT=np.where(np.isnan(t),1.0,np.clip(0.5+t/0.02,0.3,2.0))
        pos=dd["bp"]*zm*dir_scales[d]*rs*kM*kT
        pos=np.minimum(pos,MP); pos=np.minimum(pos,1.0)
        o=np.argsort(-np.nan_to_num(p,nan=-99))
        pos=pos[o]; pn=dd["pnls"][o]
        cum=np.cumsum(pos); mask=cum<=1.0
        if (~mask).any():
            fo=np.argmax(~mask); rem=1.0-(cum[fo-1] if fo>0 else 0.0); pos[fo]=max(0,rem); pos[fo+1:]=0
        capital*=1+float((pos*pn).sum()); eq.append(capital)
        tr.append((d,float((pos*pn).sum()),pos))
    return eq,tr
rows=[]
for cost in [0.00109,0.0014,0.0017,0.0020,0.00235]:
    D=build(cost); eq,tr=run(D)
    e=pd.Series(eq[1:],index=pd.to_datetime([t[0] for t in tr]))
    r=e.pct_change().fillna(0)
    yrs=(e.index[-1]-e.index[0]).days/365.25
    cg=(e.iloc[-1]/e.iloc[0])**(1/yrs)-1
    dd=((e-e.cummax())/e.cummax()).min()
    sh=r.mean()/r.std()*np.sqrt(243)
    sub=e.loc["2023-01-01":]; y3=(sub.iloc[-1]/sub.iloc[0])**(1/((sub.index[-1]-sub.index[0]).days/365.25))-1
    yr={y:(e.loc[str(y)].iloc[-1]/ (e.loc[:str(y)+"-12-31"].iloc[-2] if False else e.loc[:str(y)+"-01-01"].iloc[0]))-1 for y in range(2023,2027)}
    print(f"cost/side {cost*100:.3f}%  CAGR {cg*100:7.1f}%  MDD {dd*100:6.2f}%  Sharpe {sh:5.2f}  2023-26H1 CAGR {y3*100:7.1f}%")
    print("        yearly:", "  ".join(f"{y}:{v*100:6.1f}%" for y,v in yr.items()))
