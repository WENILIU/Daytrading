import pandas as pd, numpy as np, pickle, time, warnings; warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingRegressor
t0=time.time()
COST=0.00111  # same as v13_engine.COST
d=pd.read_pickle("universe15_nola.pkl").reset_index(drop=True)
def pnl(d,tp,sl):
    e=d["entry"].values; hi=d["day_high"].values; lo=d["day_low"].values; cl=d["day_close"].values
    lu=d["lu"].values; ld=d["ld"].values; tk=d["tick"].values
    s=(d["direction"]=="SHORT").values; out=np.zeros(len(d))
    for sh in [True,False]:
        m=s==sh
        if not m.any(): continue
        ee=e[m]
        if sh:
            tpp=ee*(1-tp); slp=np.minimum(ee*(1+sl), lu[m]-tk[m]); r=(ee-cl[m])/ee
            h=hi[m]>=slp; r[h]=-(slp[h]-ee[h])/ee[h]; hp=lo[m]<=tpp; r[hp]=tp
        else:
            tpp=ee*(1+tp); slp=np.maximum(ee*(1-sl), ld[m]+tk[m]); r=(cl[m]-ee)/ee
            h=lo[m]<=slp; r[h]=-(ee[h]-slp[h])/ee[h]; hp=hi[m]>=tpp; r[hp]=tp
        out[m]=r
    return out-2*COST
d["p12"]=pnl(d,0.12,0.04)
CAND=["adj_gap","abs_gap","zt_dist","market_ret","mkt_vol_5d","mkt_drawdown","prev3_market_ret",
 "consec_down_days","signals_today","stock_signals_30d","had_signal_yesterday",
 "month","weekday","dist_hi60","ret_20","vol_ratio","price","zt_close_20","zt_close_60",
 "gapup_60","gapdn_60","lock_rate_up_500","lock_rate_dn_500","touch_rate_up_500","touch_rate_dn_500"]
def keep(sub,cols): return [c for c in cols if pd.to_numeric(sub[c],errors="coerce").dropna().nunique()>=8]
PROD_YEAR=2026   # walk-forward model used for live = trained on year < 2026
def fit_prod(target):
    out={}
    for direc in ["SHORT","LONG"]:
        dd=d[d["direction"]==direc]; y=dd[target].values; yr=dd["year"].values
        tr=(yr<PROD_YEAR)&np.isfinite(y)
        cols=keep(dd[tr],CAND)
        X=dd[cols].apply(pd.to_numeric,errors="coerce").values
        mdl=HistGradientBoostingRegressor(max_iter=250,learning_rate=0.06,max_depth=5,
            min_samples_leaf=60,l2_regularization=1.0,random_state=0).fit(X[tr],y[tr])
        out[direc]={"model":mdl,"cols":cols,"n_train":int(tr.sum())}
        print(f"  {direc} trained on n={int(tr.sum())} cols={len(cols)} t={round(time.time()-t0)}s",flush=True)
    return out
print("pass1...",flush=True); M1=fit_prod("p12")
# reproduce walk-forward preds for the quantile pool (must match backtest exactly)
def wf_pred(target):
    pred=pd.Series(np.nan,index=d.index)
    for direc in ["SHORT","LONG"]:
        dd=d[d["direction"]==direc]; y=dd[target].values; yr=dd["year"].values
        for Y in range(2013,2027):
            tr=(yr<Y)&np.isfinite(y); te=(yr==Y)
            if tr.sum()<800 or te.sum()<20: continue
            cols=keep(dd[tr],CAND); X=dd[cols].apply(pd.to_numeric,errors="coerce").values
            m=HistGradientBoostingRegressor(max_iter=250,learning_rate=0.06,max_depth=5,
                min_samples_leaf=60,l2_regularization=1.0,random_state=0).fit(X[tr],y[tr])
            pred.loc[dd.index[te]]=m.predict(X[te])
    return pred
def causal_q(pred,minpool=500):
    q=pd.Series(0.5,index=d.index); buf=[]; pool1=np.array([]); pool2=np.array([])
    for dt in sorted(d["date"].unique()):
        idx=d.index[d["date"]==dt].values; pv=pred.loc[idx].values
        if len(buf)>=minpool:
            pool=np.sort(np.asarray(buf,dtype=float)); q.loc[idx]=np.searchsorted(pool,pv,side="left")/len(pool)
        buf.extend(pred.loc[idx].values.tolist())
        if len(buf)>60000: buf=buf[-60000:]
    return q, np.sort(np.asarray(buf,dtype=float))
p1=wf_pred("p12"); q1,pool1=causal_q(p1)
d["tp"]=np.where(q1.values>=0.85,0.20,0.12)
d["p"]=np.where(d["tp"].values>=0.20, pnl(d,0.20,0.04), pnl(d,0.12,0.04))
print("pass2...",flush=True); M2=fit_prod("p")
p2=wf_pred("p"); q2,pool2=causal_q(p2)
lad=[0.04,0.05,0.07,0.09,0.12]
bp=pd.cut(q2,[0,.20,.42,.61,.78,1.0],labels=lad).astype(float)
# trailing 30d mean realized p by direction, as of last date (for k_trail)
tr30={}
for direc in ["SHORT","LONG"]:
    s=d[d["direction"]==direc].sort_values("date")
    tr30[direc]=float(s["p"].rolling(30).mean().iloc[-1])
obj={"prod_models":M1,"prod_models2":M2,"pool1":pool1,"pool2":pool2,
     "ladder":lad,"cuts":[0,.20,.42,.61,.78,1.0],"q1_tp_threshold":0.85,
     "tp_high":0.20,"tp_low":0.12,"sl":0.04,"pred_q_min":0.20,
     "trailing30":tr30,"prod_year":PROD_YEAR,"train_end":str(d["date"].max()),
     "cand":CAND,"cost_side":COST}
pickle.dump(obj,open("v13_model.pkl","wb"))
print("SAVED v13_model.pkl  pool1",len(pool1),"pool2",len(pool2),"train_end",obj["train_end"])
print("trailing30:",{k:round(v,5) for k,v in tr30.items()})
# sanity: reproduce backtest columns
chk=pd.DataFrame({"q1":q1,"q2":q2,"base_pos":bp,"tp":d["tp"]})
ref=pd.read_pickle("signals_v13.pkl")
print("q2 corr vs backtest:",round(np.corrcoef(chk["q2"].fillna(0.5),ref["pred_q"])[0,1],5),
      " base_pos match:",round((chk["base_pos"].astype(float).values==ref["base_pos"].values).mean(),4))
