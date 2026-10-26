import pandas as pd, numpy as np, warnings, time; warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingRegressor
COST=0.00109
d=pd.read_pickle("universe3_raw.pkl").reset_index(drop=True)
d=d[d["raw_gap"].abs()>=0.03].reset_index(drop=True)  # v8 rule also requires |raw_gap|>=3%
def pnl(d,tp,sl):
    e=d["entry"].values; hi=d["day_high"].values; lo=d["day_low"].values; cl=d["day_close"].values
    lu=d["lu"].values; ld=d["ld"].values; tk=d["tick"].values
    s=(d["direction"]=="SHORT").values; out=np.zeros(len(d))
    for sh in [True,False]:
        m=s==sh
        if not m.any(): continue
        ee=e[m]
        if sh:
            tpp=ee*(1-tp); slp=np.minimum(ee*(1+sl), lu[m]-tk[m])
            r=(ee-cl[m])/ee
            h=hi[m]>=slp; r[h]=-(slp[h]-ee[h])/ee[h]
            hp=lo[m]<=tpp; r[hp]=tp
        else:
            tpp=ee*(1+tp); slp=np.maximum(ee*(1-sl), ld[m]+tk[m])
            r=(cl[m]-ee)/ee
            h=lo[m]<=slp; r[h]=-(ee[h]-slp[h])/ee[h]
            hp=hi[m]>=tpp; r[hp]=tp
        out[m]=r
    return out-2*COST
d["p12"]=pnl(d,0.12,0.04)
CAND=["adj_gap","abs_gap","zt_dist","market_ret","mkt_vol_5d","mkt_drawdown","prev3_market_ret",
 "consec_down_days","signals_today","stock_signals_30d","had_signal_yesterday",
 "month","weekday","dist_hi60","ret_20","vol_ratio","price","zt_close_20","zt_close_60",
 "gapup_60","gapdn_60","lock_rate_up_500","lock_rate_dn_500","touch_rate_up_500","touch_rate_dn_500"]
def keep(sub,cols):
    return [c for c in cols if pd.to_numeric(sub[c],errors="coerce").dropna().nunique()>=8]
def mkpred(target):
    pred=pd.Series(np.nan,index=d.index)
    for direc in ["SHORT","LONG"]:
        dd=d[d["direction"]==direc]
        y=dd[target].values; yr=dd["year"].values
        for Y in range(2013,2027):
            tr=(yr<Y)&np.isfinite(y); te=(yr==Y)
            if tr.sum()<800 or te.sum()<20: continue
            cols=keep(dd[tr],CAND)
            X=dd[cols].apply(pd.to_numeric,errors="coerce").values
            mdl=HistGradientBoostingRegressor(max_iter=250,learning_rate=0.06,max_depth=5,
                min_samples_leaf=60,l2_regularization=1.0,random_state=0).fit(X[tr],y[tr])
            pred.loc[dd.index[te]]=mdl.predict(X[te])
    return pred
def causal_q(pred, lookback=250, minpool=500):
    """percentile rank of each row's pred vs predictions from strictly earlier dates (within lookback trading days)"""
    q=pd.Series(0.5,index=d.index)
    order=sorted(d["date"].unique())
    hist=[]  # sorted list per window; rebuild per day from buffer
    buf=[]
    for i,dt in enumerate(order):
        pool=np.sort(np.asarray(buf,dtype=float)) if buf else np.array([])
        cur=d[d["date"]==dt]
        if len(pool)>=minpool:
            v=cur["pred_tmp"].values if "pred_tmp" in cur else None
        idx=cur.index.values
        pv=pred.loc[idx].values
        if len(pool)>=minpool:
            pos=np.searchsorted(pool,pv,side="left")/len(pool)
            q.loc[idx]=pos
        buf.extend(pred.loc[idx].values.tolist())
        if len(buf)>40000: buf=buf[-40000:]
    return q
t0=time.time()
print("pass1...",flush=True); d["pred1"]=mkpred("p12")
d["q1"]=causal_q(d["pred1"])
d["tp"]=np.where(d["q1"].values>=0.85,0.20,0.12)
d["p"]=np.where(d["tp"].values>=0.20, pnl(d,0.20,0.04), pnl(d,0.12,0.04))
print("pass2...",flush=True); d["pred"]=mkpred("p")
d["pred_q"]=causal_q(d["pred"])
lad=[0.04,0.05,0.07,0.09,0.12]
d["base_pos"]=pd.cut(d["pred_q"],[0,.20,.42,.61,.78,1.0],labels=lad).astype(float)
d.to_pickle("signals_v11d.pkl")
print("done",round(time.time()-t0))
s=d[d["pred"].notna()]
print("OOS IC all",round(s["pred"].corr(s["p"],method="spearman"),4))
for dr in ["SHORT","LONG"]:
    t=s[s["direction"]==dr]; print("  ",dr,round(t["pred"].corr(t["p"],method="spearman"),4),len(t))
print("base_pos dist:",d["base_pos"].value_counts().sort_index().to_dict())
print("tp20 share:",(d["tp"]>=0.2).mean())
