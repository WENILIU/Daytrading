import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
exec(open("fast_nm.py").read().split('print("="*60)')[0])
base=pd.read_pickle("signals_pred_br.pkl"); base.index=pd.read_pickle("signals_pred.pkl").index
is_s=base["direction"]=="SHORT"
base["touch_zt"]=np.where(is_s,base["day_high"]>=base["lu"]-1e-9,base["day_low"]<=base["ld"]+1e-9)
base["year"]=pd.to_datetime(base["date"]).dt.year
BP1,BP2,M1,M2,MP=0.015,0.045,10.0,2.5,0.25
IDX={d:g[d].index.values for d in g}
DATES=[d for d in dates if d in IDX]
PX={d:base.loc[v,"entry"].values for d,v in IDX.items()}
BPv={d:base.loc[v,"base_pos"].values for d,v in IDX.items()}
ZD={d:base.loc[v,"zt_dist"].values for d,v in IDX.items()}
PRd={d:np.asarray(base.loc[v,"pred_br"].values,dtype=float) for d,v in IDX.items()}
DS={d:dir_scales[d] for d in DATES}

def build(cost):
    df=base.copy()
    df["p"]=np.where(df["score"].values>=3,calc_pnl_vec(df,0.20,0.04),calc_pnl_vec(df,0.12,0.04))-2*cost
    trail={}
    for direc in ["SHORT","LONG"]:
        s=df[df["direction"]==direc].sort_values("date")
        s["t30"]=s["p"].rolling(30,min_periods=30).mean().shift(1)
        for dt,x in zip(s["date"],s["t30"].values): trail[(dt,direc)]=x
    PN={d:df.loc[v,"p"].values for d,v in IDX.items()}
    T3={d:np.array([trail.get((d,x),np.nan) for x in df.loc[v,"direction"]],dtype=float) for d,v in IDX.items()}
    return PN,T3

def run(cost):
    PN,T3=build(cost)
    capital=CAPITAL; eq=[CAPITAL]; rows=[]
    for d in DATES:
        peak=max(eq); cdd=(capital-peak)/peak
        rs=0.12 if cdd<-0.012 else (0.3 if cdd<-0.006 else 1.0)
        p=PRd[d]; kM=np.where(np.isfinite(p),np.clip(0.5+np.nan_to_num(p)/0.02,0,2),1.0)
        t=T3[d]; kT=np.where(np.isnan(t),1.0,np.clip(0.5+t/0.02,0.3,2.0))
        zm=np.where(ZD[d]<BP1,M1,np.where(ZD[d]<BP2,M2,1.0))
        pos=BPv[d]*zm*DS[d]*rs*kM*kT; pos=np.minimum(pos,MP)
        o=np.argsort(-np.nan_to_num(p,nan=-99)); pos=pos[o]; pn=PN[d][o]; px=PX[d][o]
        rem=capital; w=[];r=[]
        for i in range(len(pos)):
            if pos[i]<=0: continue
            sh=int(pos[i]*capital/(px[i]*1000))*1000
            if sh<1000: continue
            if sh*px[i]>rem:
                sh=int(rem/(px[i]*1000))*1000
                if sh<1000: continue
            rem-=sh*px[i]; w.append(sh*px[i]); r.append(pn[i])
        if not w: eq.append(capital); rows.append((d,0,0.0)); continue
        pnl=float((np.array(w)*np.array(r)).sum()/capital)
        capital*=(1+pnl); eq.append(capital); rows.append((d,len(w),pnl))
    dts=pd.DatetimeIndex([pd.Timestamp(x[0]) for x in rows])
    return pd.Series(eq[1:],index=dts),rows

print("成本/邊      CAGR     MDD   Sharpe   2023-26H1 CAGR   2025報酬   2025均PnL")
for cost in [0.00109,0.00140,0.00170,0.00200,0.00235]:
    e,rows=run(cost)
    rr=e.pct_change().fillna(0); yrs=(e.index[-1]-e.index[0]).days/365.25
    cg=(e.iloc[-1]/e.iloc[0])**(1/yrs)-1; dd=((e-e.cummax())/e.cummax()).min()
    s=e.loc["2023-01-01":]; yy=(s.index[-1]-s.index[0]).days/365.25
    rc=(s.iloc[-1]/s.iloc[0])**(1/yy)-1
    y25=[x[2] for x in rows if pd.Timestamp(x[0]).year==2025]
    r25=np.prod([1+v for v in y25])-1
    print(f"{cost*100:.3f}%   {cg*100:7.1f}% {dd*100:7.2f}% {rr.mean()/rr.std()*np.sqrt(243):7.2f}   {rc*100:10.1f}%   {r25*100:8.1f}%")
