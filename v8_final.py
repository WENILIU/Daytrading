import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
exec(open("fast_nm.py").read().split('print("="*60)')[0])

df=pd.read_pickle("signals_pred_br.pkl"); df.index=pd.read_pickle("signals_pred.pkl").index
df["p"]=np.where(df["score"].values>=3,calc_pnl_vec(df,0.20,0.04),calc_pnl_vec(df,0.12,0.04))-2*COST
is_s=df["direction"]=="SHORT"
df["touch_zt"]=np.where(is_s,df["day_high"]>=df["lu"]-1e-9,df["day_low"]<=df["ld"]+1e-9)
df["year"]=pd.to_datetime(df["date"]).dt.year
BP1,BP2,M1,M2,MP=0.015,0.045,10.0,2.5,0.25
trail={}
for direc in ["SHORT","LONG"]:
    s=df[df["direction"]==direc].sort_values("date")
    s["t30"]=s["p"].rolling(30,min_periods=30).mean().shift(1)
    for dt,x in zip(s["date"],s["t30"].values): trail[(dt,direc)]=x
DD={}
for d in dates:
    if d not in g: continue
    sub=g[d]; ix=sub.index.values
    DD[d]={"bp":df.loc[ix,"base_pos"].values,"zt_d":df.loc[ix,"zt_dist"].values,
      "dirs":df.loc[ix,"direction"].values,"pnls":df.loc[ix,"p"].values,
      "pr":np.asarray(df.loc[ix,"pred_br"].values,dtype=float),
      "entry_px":df.loc[ix,"entry"].values,"idx":ix,
      "zt":df.loc[ix,"touch_zt"].values,"yr":df.loc[ix,"year"].values,
      "t30":np.array([trail.get((d,x),np.nan) for x in df.loc[ix,"direction"]],dtype=float)}

def run(lot=True):
    capital=CAPITAL; equity=[CAPITAL]; trades=[]
    for d in dates:
        if d not in DD: equity.append(capital); continue
        dd=DD[d]; peak=max(equity); cdd=(capital-peak)/peak
        rs=0.12 if cdd<-0.012 else (0.3 if cdd<-0.006 else 1.0)
        zm=np.where(dd["zt_d"]<BP1,M1,np.where(dd["zt_d"]<BP2,M2,1.0))
        p=dd["pr"]; kM=np.where(np.isfinite(p),np.clip(0.5+np.nan_to_num(p)/0.02,0,2),1.0)
        t=dd["t30"]; kT=np.where(np.isnan(t),1.0,np.clip(0.5+t/0.02,0.3,2.0))
        pos=dd["bp"]*zm*dir_scales[d]*rs*kM*kT
        pos=np.minimum(pos,MP); pos=np.minimum(pos,1.0)
        o=np.argsort(-np.nan_to_num(p,nan=-99))
        pos=pos[o]; pn=dd["pnls"][o]; dr_=dd["dirs"][o]; zt=dd["zt"][o]; px=dd["entry_px"][o]; idy=dd["idx"][o]
        if lot:
            rem=capital; w=[]; r=[]; keep=[]
            for i in range(len(pos)):
                if pos[i]<=0: continue
                tgt=pos[i]*capital
                sh=int(tgt/(px[i]*1000))*1000
                if sh<1000: continue
                if sh*px[i]>rem:
                    sh=int(rem/(px[i]*1000))*1000
                    if sh<1000: continue
                rem-=sh*px[i]; w.append(sh*px[i]); r.append(pn[i]); keep.append(i)
            if not w:
                equity.append(capital); trades.append((d,0,0.0,0.0,dr_[:0],pn[:0],pos[:0],zt[:0],dd["yr"][0],0))
                continue
            w=np.array(w); r=np.array(r)
            pnl=float((w*r).sum()/capital)
            expo=float(w.sum()/capital)
            sel=np.array(keep)
            trades.append((d,len(w),pnl,expo,dr_[sel],pn[sel],w/capital,zt[sel],dd["yr"][0],int((pos>0).sum())-len(w)))
        else:
            cum=np.cumsum(pos); mask=cum<=1.0
            if (~mask).any():
                fo=np.argmax(~mask); rem=1.0-(cum[fo-1] if fo>0 else 0.0); pos[fo]=max(0.0,rem); pos[fo+1:]=0
            pnl=float((pos*pn).sum()); expo=float(pos.sum())
            sel=np.where(pos>0)[0]
            trades.append((d,len(sel),pnl,expo,dr_[sel],pn[sel],pos[sel],zt[sel],dd["yr"][0],0))
        capital*=(1+pnl); equity.append(capital)
    return np.array(equity),trades

out={}
for lot,lab in [(True,"整張"),(False,"零股(分數)")]:
    eq,tr=run(lot); out[lab]=(eq,tr)
    pickle.dump({"eq":eq,"tr":tr},open("v8_lot_%s.pkl"%("1" if lot else "0"),"wb"))
pickle.dump({k:v[0] for k,v in out.items()},open("v8_eq_curves.pkl","wb"))
print("done")
for lab,(eq,tr) in out.items():
    rr=pd.Series(eq).pct_change().fillna(0)
    yrs=(pd.Timestamp(dates[-1])-pd.Timestamp(dates[0])).days/365.25
    cg=(eq[-1]/CAPITAL)**(1/yrs)-1
    e=pd.Series(eq); dd=((e-e.cummax())/e.cummax()).min()
    n=sum(x[1] for x in tr)
    print(f"{lab:<10} CAGR {cg*100:7.1f}%  MDD {dd*100:6.2f}%  Sharpe {rr.mean()/rr.std()*np.sqrt(243):5.2f}  筆 {n:6d}  終值 {eq[-1]/CAPITAL:,.0f}x")
