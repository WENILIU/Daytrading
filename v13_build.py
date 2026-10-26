import pandas as pd, numpy as np, pickle, time, warnings; warnings.filterwarnings("ignore")
t0=time.time()
from finlab import data
op=data.get("price:開盤價"); hp=data.get("price:最高價"); lp=data.get("price:最低價"); cp=data.get("price:收盤價"); tv=data.get("price:成交金額")
stocks=op.columns.astype(str); cal=pd.DatetimeIndex(sorted(op.index))
# market opening gap from 0050 (observable at 09:00)
mo=op["0050"].values; mc=cp["0050"].values
pmc=np.roll(mc,1,axis=0); pmc[0]=np.nan
mktgap=mo/pmc-1.0
mktgap=np.nan_to_num(mktgap,nan=0.0)
print("market gap stats: mean",round(mktgap.mean(),5),"std",round(mktgap.std(),5),"|x|>1%",round((np.abs(mktgap)>0.01).mean()*100,1),"%",flush=True)
OP=op.values; HP=hp.values; LP=lp.values; CP=cp.values; TV=tv.values
pc=np.roll(CP,1,axis=0); pc[0]=np.nan; ptv=np.roll(TV,1,axis=0); ptv[0]=np.nan
mv=mktgap[:,None]
gap=OP/pc-1.0; adj=gap-mv
def tsz(p):
    if p<10: return 0.05
    if p<50: return 0.05
    if p<100: return 0.1
    if p<500: return 0.5
    if p<1000: return 1.0
    if p<5000: return 5.0
    return 10.0
t=np.vectorize(tsz)(pc); LU=np.floor(pc*1.10/t)*t; LD=np.ceil(pc*0.90/t)*t
TK=np.vectorize(tsz)(OP)
A=np.abs(adj); short=adj>0
ztd=np.where(short,(LU-OP)/np.where(OP==0,1,OP),(OP-LD)/np.where(OP==0,1,OP))
base=(A>=0.015)&(OP>=30)&(ptv>=1e7)&np.isfinite(pc)&np.isfinite(OP)&(ztd>0)
base&= ~((OP>=LU)|(OP<=LD))
base&= np.where(short, A>=0.015, A>=0.05)
DP=pd.read_pickle("disposal_panel_full.pkl"); DP["stock"]=DP["stock"].astype(str)
smap={s:i for i,s in enumerate(stocks)}; dmap={d:i for i,d in enumerate(cal)}
DP["si"]=DP["stock"].map(smap); DP["di"]=DP["date"].map(dmap)
dd=DP.dropna(subset=["si","di"])
disp=np.zeros(OP.shape,bool); disp[dd["di"].astype(int).values,dd["si"].astype(int).values]=True
base&= ~disp
print("universe rows:",int(base.sum()),flush=True)
ri,ci=np.nonzero(base)
out=pd.DataFrame({
 "date":cal[ri],"stock":stocks[ci],
 "direction":np.where(short[ri,ci],"SHORT","LONG"),
 "raw_gap":gap[ri,ci],"adj_gap":adj[ri,ci],"market_ret":mv[ri,0],
 "entry":OP[ri,ci],"day_high":HP[ri,ci],"day_low":LP[ri,ci],"day_close":CP[ri,ci],
 "prev_close":pc[ri,ci],"prev_turnover":ptv[ri,ci],
 "lu":LU[ri,ci],"ld":LD[ri,ci],"tick":TK[ri,ci],"zt_dist":ztd[ri,ci]})
out["abs_gap"]=out["adj_gap"].abs()
out=out.sort_values(["date","stock"]).reset_index(drop=True)
out["year"]=pd.to_datetime(out["date"]).dt.year; out["month"]=out["date"].dt.month; out["weekday"]=out["date"].dt.weekday
print("built",len(out),round(time.time()-t0,1),"s",out["direction"].value_counts().to_dict(),flush=True)
c30=np.zeros(len(out)); hy=np.zeros(len(out),bool)
dv=out["date"].values; sv=out["stock"].values
calD=np.sort(np.unique(dv)); pos={d:i for i,d in enumerate(calD)}
order=np.argsort(sv,kind="stable")
for st,idx0 in pd.Series(order).groupby(sv[order]):
    idx=idx0.values; ds=np.array([pos[x] for x in dv[idx]],dtype=np.int64)
    for k in range(1,len(idx)):
        i=idx[k]; w=ds[:k]
        c30[i]=int(((ds[k]-w)<=30).sum()); hy[i]=bool((ds[k]-w[-1])==1)
out["stock_signals_30d"]=c30; out["had_signal_yesterday"]=hy.astype(int)
out["signals_today"]=out.groupby("date")["stock"].transform("size")
print("set features",round(time.time()-t0,1),flush=True)
# market extras (all based on PRIOR closes -> no look-ahead)
mret=pd.Series(mc,cal).pct_change().values
mcl=pd.Series(mc,cal)
MT=pd.DataFrame(index=cal)
MT["mkt_vol_5d"]=mcl.pct_change().rolling(5).std().shift(1).values
MT["mkt_drawdown"]=(mcl/mcl.cummax()-1).shift(1).values
MT["prev3_market_ret"]=mcl.pct_change().rolling(3).sum().shift(1).values
sgn=np.sign(mcl.pct_change().values)
cd=np.zeros(len(cal)); cur=0
for i in range(len(cal)):
    if sgn[i]<0: cur+=1
    elif sgn[i]>0: cur=0
    cd[i]=cur
MT["consec_down_days"]=pd.Series(cd,cal).shift(1).values
for c in MT.columns: out[c]=MT[c].reindex(out["date"]).values
print("market features",round(time.time()-t0,1),flush=True)
z=pickle.load(open(r"D:\gapfade_data\zt_factors.pkl","rb"))
ZF=["lock_rate_up_250","touch_rate_up_250","lock_rate_dn_250","touch_rate_dn_250",
    "lock_rate_up_500","touch_rate_up_500","lock_rate_dn_500","touch_rate_dn_500",
    "zt_close_20","zt_close_60","gapup_60","gapdn_60","vol_ratio","ret_20","dist_hi60","price"]
ov=out["stock"].values; odv=out["date"].values
for c in ZF:
    W=pd.DataFrame(z[c]); W.index=pd.to_datetime(W.index)
    wi={d:i for i,d in enumerate(W.index.values)}; wc={s:j for j,s in enumerate(W.columns.astype(str))}
    A2=W.values
    ridx=np.fromiter((wi.get(x,-1) for x in odv),dtype=np.int64,count=len(odv))
    cidx=np.fromiter((wc.get(x,-1) for x in ov),dtype=np.int64,count=len(ov))
    ok=(ridx>=0)&(cidx>=0); vals=np.full(len(out),np.nan)
    vals[ok]=A2[ridx[ok],cidx[ok]]; out[c]=vals
out.to_pickle("universe15_nola.pkl")
print("SAVED universe15_nola.pkl",len(out),round(time.time()-t0,1),"s")
