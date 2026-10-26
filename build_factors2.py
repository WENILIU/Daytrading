import pandas as pd, numpy as np, pickle, warnings, time; warnings.filterwarnings("ignore")
D=r"D:\AI專案\StockAgent\finlab\database"
C=pd.read_pickle(D+r"\price_close.pkl").astype(float)
H=pd.read_pickle(D+r"\price_high.pkl").astype(float)
L=pd.read_pickle(D+r"\price_low.pkl").astype(float)
O=pd.read_pickle(D+r"\price_open.pkl").astype(float)
V=pd.read_pickle(D+r"\price_vol.pkl").astype(float)
PC=C.shift(1); valid=PC.notna()&(PC>0)
tick=pd.DataFrame(np.select([PC.values<10,PC.values<100,PC.values<500,PC.values<1000,PC.values<5000],
        [0.05,0.1,0.5,1.0,5.0],10.0),index=PC.index,columns=PC.columns)
LU=pd.DataFrame(np.floor(PC.values*1.10/tick.values)*tick.values,index=PC.index,columns=PC.columns)
LD=pd.DataFrame(np.ceil(PC.values*0.90/tick.values)*tick.values,index=PC.index,columns=PC.columns)
up_t=(H.values>=LU.values-1e-9)&valid.values
up_l=(C.values>=LU.values-1e-9)&valid.values
dn_t=(L.values<=LD.values+1e-9)&valid.values
dn_l=(C.values<=LD.values+1e-9)&valid.values
gu=(O.values>=PC.values*1.05)&valid.values
gd=(O.values<=PC.values*0.95)&valid.values
print("upT",up_t.sum(),"upL",up_l.sum(),"dnT",dn_t.sum(),"dnL",dn_l.sum())
idx,cols=C.index,C.columns
def mk(a): return pd.DataFrame(np.asarray(a,dtype=float),index=idx,columns=cols)
def rate(n,d,win,mind):
    a=mk(n).rolling(win).sum(); b=mk(d).rolling(win).sum()
    return (a/b).where(b>=mind)
f={}
for w,md in [(250,3),(500,5)]:
    f[f"lock_rate_up_{w}"]=rate(up_t,up_t,w,md)
    f[f"touch_rate_up_{w}"]=rate(up_t&gu,gu,w,md)
    f[f"lock_rate_dn_{w}"]=rate(dn_t,dn_t,w,md)
    f[f"touch_rate_dn_{w}"]=rate(dn_t&gd,gd,w,md)
f["zt_close_20"]=mk(up_l).rolling(20).sum()
f["zt_close_60"]=mk(up_l).rolling(60).sum()
f["gapup_60"]=mk(gu).rolling(60).sum()
f["gapdn_60"]=mk(gd).rolling(60).sum()
f["vol_ratio"]=V/V.rolling(20).mean()
f["ret_20"]=C/C.shift(20)-1
f["dist_hi60"]=C/C.rolling(60).max()-1
f["price"]=C
for k in list(f): f[k]=f[k].shift(1)
pickle.dump(f,open("zt_factors.pkl","wb"))
print("built",len(f))
for k,v in f.items(): print(f"  {k:<20} cov {100*v.notna().values.mean():>5.1f}%")
