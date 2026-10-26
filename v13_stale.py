import pandas as pd, numpy as np, pickle, warnings; warnings.filterwarnings("ignore")
exec(open("v13_dstune.py",encoding="utf-8").read().split("d=pd.read_pickle")[0])
base=pd.read_pickle("signals_v13.pkl"); base=base[base["pred"].notna()].copy()
base["stock"]=base["stock"].astype(str)
ZF=["lock_rate_up_250","touch_rate_up_250","lock_rate_dn_250","touch_rate_dn_250",
    "lock_rate_up_500","touch_rate_up_500","lock_rate_dn_500","touch_rate_dn_500",
    "zt_close_20","zt_close_60","gapup_60","gapdn_60","vol_ratio","ret_20","dist_hi60","price"]
z=pickle.load(open(r"D:\gapfade_data\zt_factors.pkl","rb"))
def stale(d,N):
    if N==0: return d
    out=d.copy()
    for c in ZF:
        if c not in out.columns: continue
        W=pd.DataFrame(z[c]); W.index=pd.to_datetime(W.index)
        Ws=W.shift(N)                      # value used = N trading days older
        wi={x:i for i,x in enumerate(Ws.index.values)}; wc={s:j for j,s in enumerate(Ws.columns.astype(str))}
        ridx=np.fromiter((wi.get(x,-1) for x in out["date"]),dtype=np.int64,count=len(out))
        cidx=np.fromiter((wc.get(x,-1) for x in out["stock"]),dtype=np.int64,count=len(out))
        ok=(ridx>=0)&(cidx>=0); v=np.full(len(out),np.nan)
        A=Ws.values; v[ok]=A[ridx[ok],cidx[ok]]
        out[c]=v
    return out
print("factor staleness sensitivity (bpm=1.0, ds removed). N = trading days the factor panel lags")
for N in [0,5,20,40,60]:
    d=stale(base,N); d["touch_zt"]=np.where(d["direction"]=="SHORT",d["day_high"]>=d["lu"]-1e-9,d["day_low"]<=d["ld"]+1e-9)
    p=perf(run(d,bpmul=1.0,dsfac=1.0))
    print(f"  lag {N:>3}d ({N/20:.0f}mo): CAGR {p['cagr']:7.1f}%  MDD {p['mdd']:6.2f}%  Sharpe {p['sharpe']:5.2f}  2023-25 {p['seg23']:7.1f}%")
