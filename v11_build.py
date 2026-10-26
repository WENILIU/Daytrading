import pandas as pd, numpy as np, math, pickle, warnings, time; warnings.filterwarnings("ignore")
t00=time.time()
d3=pd.read_pickle("gap_fade_signals_3pct_raw.pkl")
d3["date"]=pd.to_datetime(d3["date"]); d3["stock"]=d3["stock"].astype(str)
b5=pd.read_pickle("gap_fade_signals_scored_filtered.pkl").copy(); b5["date"]=pd.to_datetime(b5["date"]); b5["stock"]=b5["stock"].astype(str)
MF=["market_ret","mkt_vol_5d","mkt_drawdown","prev3_market_ret","consec_down_days"]
M=b5.drop_duplicates("date").set_index("date")[MF].sort_index()
cal=pd.DatetimeIndex(sorted(d3["date"].unique()))
M=M.reindex(cal).ffill()
print("market table ready",len(M),flush=True)
def tsz(p):
    if p<10: return 0.05
    if p<50: return 0.05
    if p<100: return 0.1
    if p<500: return 0.5
    if p<1000: return 1.0
    if p<5000: return 5.0
    return 10.0
pc=d3["prev_close"].values
d3["lu"]=np.array([round(math.floor(x*1.10/tsz(x))*tsz(x),2) for x in pc])
d3["ld"]=np.array([round(math.ceil(x*0.90/tsz(x))*tsz(x),2) for x in pc])
d3["tick"]=np.array([tsz(x) for x in d3["entry"].values])
d3["abs_gap"]=d3["adj_gap"].abs()
is_s=(d3["direction"]=="SHORT").values
d3["zt_dist"]=np.where(is_s,(d3["lu"]-d3["entry"])/d3["entry"],(d3["entry"]-d3["ld"])/d3["entry"])
atlim=np.where(is_s,d3["entry"]>=d3["lu"],d3["entry"]<=d3["ld"])
d3=d3[~atlim]
d3=d3[(d3["entry"]>=30)&(d3["prev_turnover"]>=3_000_000)].copy()
d3["month"]=d3["date"].dt.month; d3["weekday"]=d3["date"].dt.weekday
d3["year"]=d3["date"].dt.year
# set-dependent features (definitions verified exact)
d3=d3.sort_values(["date","stock"]).reset_index(drop=True)
d3["signals_today"]=d3.groupby("date")["stock"].transform("size")
prev={}; c30=np.zeros(len(d3)); hy=np.zeros(len(d3),bool)
for i,(dt,stk) in enumerate(zip(d3["date"].values,d3["stock"].values)):
    lst=prev.setdefault(stk,[])
    c30[i]=sum(1 for x in lst if 0<(dt-x).astype("timedelta64[D]").astype(int)<=30)
    hy[i]=any(0<(dt-x).astype("timedelta64[D]").astype(int)<=1 for x in lst)
    lst.append(dt)
d3["stock_signals_30d"]=c30; d3["had_signal_yesterday"]=hy.astype(int)
print("set features done",time.time()-t00,flush=True)
# market features
for c in MF: d3[c]=M[c].reindex(d3["date"]).values
# stock factors from wide panels
z=pickle.load(open("zt_factors.pkl","rb"))
ZF=["lock_rate_up_250","touch_rate_up_250","lock_rate_dn_250","touch_rate_dn_250",
    "lock_rate_up_500","touch_rate_up_500","lock_rate_dn_500","touch_rate_dn_500",
    "zt_close_20","zt_close_60","gapup_60","gapdn_60","vol_ratio","ret_20","dist_hi60","price"]
for c in ZF:
    W=pd.DataFrame(z[c]); W.index=pd.to_datetime(W.index)
    vals=np.full(len(d3),np.nan)
    di={d:i for i,d in enumerate(W.index.values)}; cols={c2:j for j,c2 in enumerate(W.columns.astype(str))}
    A=W.values
    for i,(dt,stk) in enumerate(zip(d3["date"].values,d3["stock"].values)):
        r=di.get(dt); 
        if r is None: continue
        j=cols.get(stk)
        if j is None: continue
        vals[i]=A[r,j]
    d3[c]=vals
    print("  factor",c,"coverage",round(float(np.isfinite(vals).mean()),3),flush=True)
d3.to_pickle("universe3_raw.pkl")
print("saved",len(d3),"in",round(time.time()-t00,1),"s")
