import pickle, numpy as np, pandas as pd
o=pickle.load(open("v8_full.pkl","rb")); eq=np.asarray(o["eq"],float); tr=o["tr"]
dts=[t[0] for t in tr]
print("eq len",len(eq),"tr len",len(tr),"first",dts[0],"last",dts[-1])
# sanity: eq[i+1] ~ eq[i]*(1+pnl)
chk=[abs(eq[i+1]/eq[i]-(1+tr[i][2])) for i in range(0,50)]
print("max recon err", max(chk))
e=pd.Series(eq[1:],index=pd.to_datetime(dts))
r=e.pct_change().fillna(0)
def rollcagr(nyr):
    n=int(nyr*243)
    out=e.shift(n)
    q=(e/out)**(1/nyr)-1
    return q.dropna()
for ny in [1,2,3]:
    q=rollcagr(ny)
    print(f"--- rolling {ny}y CAGR: n={len(q)} pos={(q>0).mean()*100:.1f}% min={q.min()*100:.1f}% p5={q.quantile(0.05)*100:.1f}% median={q.median()*100:.1f}%")
print()
print("=== 區間 CAGR（真實起訖） ===")
for a,b in [("2010-01-01","2019-12-31"),("2019-01-01","2021-12-31"),("2020-01-01","2022-12-31"),("2021-01-01","2023-12-31"),("2022-01-01","2024-12-31"),("2023-01-01","2024-12-31"),("2023-01-01","2025-12-31"),("2024-01-01","2025-12-31"),("2025-01-01","2026-06-18"),("2010-01-01","2026-06-18")]:
    s=e.loc[a:b]
    yrs=(s.index[-1]-s.index[0]).days/365.25
    cg=(s.iloc[-1]/s.iloc[0])**(1/yrs)-1
    dd=((s-s.cummax())/s.cummax()).min()
    shar=r.loc[a:b].mean()/r.loc[a:b].std()*np.sqrt(243)
    print(f"{a[:7]}~{b[:7]}  {yrs:5.2f}y  CAGR {cg*100:7.1f}%  MDD {dd*100:6.2f}%  Sharpe {shp if False else shar:5.2f}")
