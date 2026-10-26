import pandas as pd, numpy as np, pickle, warnings; warnings.filterwarnings("ignore")
M=pickle.load(open("v13_model.pkl","rb"))
d=pd.read_pickle("signals_v13.pkl"); d["stock"]=d["stock"].astype(str)
d=d[d["date"]>="2026-01-01"].copy()
ZF=["lock_rate_up_250","touch_rate_up_250","lock_rate_dn_250","touch_rate_dn_250",
    "lock_rate_up_500","touch_rate_up_500","lock_rate_dn_500","touch_rate_dn_500",
    "zt_close_20","zt_close_60","gapup_60","gapdn_60","vol_ratio","ret_20","dist_hi60","price"]
z=pickle.load(open(r"D:\gapfade_data\zt_factors.pkl","rb"))
def apply_lag(df,N):
    out=df.copy()
    for c in ZF:
        if c not in out.columns: continue
        W=pd.DataFrame(z[c]); W.index=pd.to_datetime(W.index); A=W.shift(N).values
        wi={x:i for i,x in enumerate(W.index.values)}; wc={s:j for j,s in enumerate(W.columns.astype(str))}
        ridx=np.fromiter((wi.get(x,-1) for x in out["date"]),dtype=np.int64,count=len(out))
        cidx=np.fromiter((wc.get(x,-1) for x in out["stock"]),dtype=np.int64,count=len(out))
        ok=(ridx>=0)&(cidx>=0); v=np.full(len(out),np.nan); v[ok]=A[ridx[ok],cidx[ok]]; out[c]=v
    return out
def qpool(pool,pv): 
    p=np.sort(pool); return np.searchsorted(p,pv,side="left")/len(p)
def infer(df):
    pr1=pd.Series(np.nan,index=df.index); pr2=pd.Series(np.nan,index=df.index)
    for direc in ["SHORT","LONG"]:
        m=df["direction"]==direc
        if m.sum()==0: continue
        for tag,key,slot in [(1,"prod_models","pr1"),(2,"prod_models2","pr2")]:
            e=M[key][direc]; cols=e["cols"]
            X=df.loc[m,cols].apply(pd.to_numeric,errors="coerce").values
            pv=e["model"].predict(X)
            if tag==1: pr1.loc[m]=pv
            else: pr2.loc[m]=pv
    return pr1,pr2
rows=[]
for N in [0,20,40,60]:
    df=apply_lag(d,N)
    p1,p2=infer(df)
    q1=qpool(M["pool1"],p1.values); q2=qpool(M["pool2"],p2.values)
    sel=q2>=M["pred_q_min"]
    lad=np.asarray(M["ladder"],dtype=float)
    bp=np.select([q2<c for c in M["cuts"][1:]],lad,default=lad[0])
    tp=np.where(q1>=M["q1_tp_threshold"],M["tp_high"],M["tp_low"])
    # exposure-weighted realized edge of the SELECTED set (proxy for strategy quality)
    w=bp[sel]; r=df["p"].values[sel]
    ic=float(np.corrcoef(p2.values[sel],df["p"].values[sel])[0,1]) if sel.sum()>50 else np.nan
    ref=np.asarray(df["base_pos"].values,dtype=float)
    mae=float(np.abs(bp-ref).mean())*100
    agree=float((sel==(df["pred_q"].values>=0.20)).mean())*100
    rows.append((N,int(sel.sum()),float(np.average(r,weights=w))*100,float(r.mean())*100,
                 float((r>0).mean())*100,ic,mae,agree))
t=pd.DataFrame(rows,columns=["lag_days","selected","expoWtdEdge%","meanEdge%","win%","IC","basePosMAE_pp","selAgree%"])
print("PRODUCTION MODEL on 2026 OOS -- factor staleness impact")
print(t.to_string(index=False,float_format=lambda v:f"{v:9.3f}"))
