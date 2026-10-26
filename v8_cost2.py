import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
exec(open("fast_nm.py").read().split("print(\"=\"*60)")[0])
df=pd.read_pickle("signals_pred_br.pkl"); df.index=pd.read_pickle("signals_pred.pkl").index
raw=np.where(df["score"].values>=3,calc_pnl_vec(df,0.20,0.04),calc_pnl_vec(df,0.12,0.04))
df["raw"]=raw
is_s=df["direction"]=="SHORT"
df["touch_zt"]=np.where(is_s,df["day_high"]>=df["lu"]-1e-9,df["day_low"]<=df["ld"]+1e-9)
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
        tr.append((d,float((pos*pn).sum()),int((pos>0).sum()),float(pos.sum()),float(np.mean(pn[pos>0])) if (pos>0).any() else 0.0,int(np.sum((pn>0)&(pos>0))),int((pos>0).sum())))
    return eq,tr
res={}
for cost in [0.00109,0.00235]:
    D=build(cost); eq,tr=run(D)
    e=pd.Series(eq[1:],index=pd.to_datetime([t[0] for t in tr]))
    T=pd.DataFrame(tr,columns=["date","pnl","n","expo","avgpnl","win","ntot"]); T["date"]=pd.to_datetime(T["date"]); T["year"]=T["date"].dt.year
    res[cost]=(e,T)
print("年    cost0.109%           |  cost0.235%")
print("     報酬%   MDD%  勝率% 均PnL% | 報酬%   MDD%  勝率% 均PnL%")
for y in range(2010,2027):
    out=[]
    for cost in [0.00109,0.00235]:
        e,T=res[cost]
        s=e.loc[str(y)]; prev=e.loc[:str(y)+"-12-31"].iloc[-2] if y>2010 else CAPITAL
        ret=s.iloc[-1]/prev-1
        mdd=((s-s.cummax())/s.cummax()).min()
        t=T[T["year"]==y]
        wr=t["win"].sum()/t["ntot"].sum()*100
        ap=t["avgpnl"].mean()*100
        out.append((ret*100,mdd*100,wr,ap))
    print(f"{y}  {out[0][0]:7.1f} {out[0][1]:6.1f} {out[0][2]:5.1f} {out[0][3]:6.2f} | {out[1][0]:7.1f} {out[1][1]:6.1f} {out[1][2]:5.1f} {out[1][3]:6.2f}")
