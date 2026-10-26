import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
CAPITAL=4_500_000
d=pd.read_pickle("signals_v11d.pkl"); d["stock"]=d["stock"].astype(str)
fl=pd.read_pickle("gap_fade_signals_filtered.pkl"); fl["stock"]=fl["stock"].astype(str)
flk={(a,b):(c,e,f) for a,b,c,e,f in zip(fl["date"],fl["stock"],fl["is_disposed"],fl["not_borrowable"],fl["low_turnover"])}
g=[flk.get(k) for k in zip(d["date"],d["stock"])]
d["flagged"]=[bool(x) and (x[0] or x[1] or x[2]) for x in g]
BP1,BP2,M1,M2,MP=0.015,0.045,10.0,2.5,0.25
def run(u):
    u=u[u["pred_q"]>=0.20]
    tr={}
    for direc in ["SHORT","LONG"]:
        s=u[u["direction"]==direc].sort_values("date")
        s["t30"]=s["p"].rolling(30,min_periods=30).mean().shift(1)
        for dt,x in zip(s["date"],s["t30"].values): tr[(dt,direc)]=x
    G={dt:sub for dt,sub in u.groupby("date")}
    ds={dt:(0.5 if (sub["direction"]=="SHORT").mean()>0.8 or (sub["direction"]=="SHORT").mean()<0.2 else 1.0) for dt,sub in G.items()}
    cap=CAPITAL; eq=[CAPITAL]; rows=[]
    for dt in sorted(G):
        sub=G[dt]; peak=max(eq); cdd=(cap-peak)/peak
        rs=0.12 if cdd<-0.012 else (0.3 if cdd<-0.006 else 1.0)
        zd=sub["zt_dist"].values
        zm=np.where(zd<BP1,M1,np.where(zd<BP2,M2,1.0))
        p=np.asarray(sub["pred"].values,dtype=float)
        kM=np.where(np.isfinite(p),np.clip(0.5+np.nan_to_num(p)/0.02,0,2),1.0)
        t=np.array([tr.get((dt,x),np.nan) for x in sub["direction"]],dtype=float)
        kT=np.where(np.isnan(t),1.0,np.clip(0.5+t/0.02,0.3,2.0))
        pos=np.asarray(sub["base_pos"].values,dtype=float)*zm*ds[dt]*rs*kM*kT
        pos=np.minimum(pos,MP); pos=np.minimum(pos,1.0)
        o=np.argsort(-np.nan_to_num(p,nan=-99))
        pos=pos[o]; pn=sub["p"].values[o]
        cum=np.cumsum(pos); mask=cum<=1.0
        if (~mask).any():
            fo=np.argmax(~mask); rem=1.0-(cum[fo-1] if fo>0 else 0.0); pos[fo]=max(0,rem); pos[fo+1:]=0
        cap*=1+float((pos*pn).sum()); eq.append(cap)
        rows.append((dt,float((pos*pn).sum()),int((pos>0).sum()),float(pos.sum())))
    return pd.Series(eq[1:],index=pd.to_datetime([r[0] for r in rows])),rows
base=d[~d["flagged"] & d["pred"].notna()]
CFG=[("v11 5%+ / 300萬",base[base["abs_gap"]>=0.05]),
     ("v11 3%+ / 300萬",base),
     ("v11 5%+ / 1000萬",base[(base["abs_gap"]>=0.05)&(base["prev_turnover"]>=1e7)]),
     ("v11 3%+ / 1000萬",base[base["prev_turnover"]>=1e7])]
out={}
for nm,u in CFG:
    e,rows=run(u); out[nm]=(e,rows)
    r=e.pct_change().fillna(0); yrs=(e.index[-1]-e.index[0]).days/365.25
    cg=(e.iloc[-1]/e.iloc[0])**(1/yrs)-1; dd=((e-e.cummax())/e.cummax()).min()
    print(f"{nm:<20} CAGR {cg*100:7.1f}%  MDD {dd*100:6.2f}%  Sharpe {r.mean()/r.std()*np.sqrt(243):5.2f}  筆{sum(x[2] for x in rows):6d}")
print()
print("逐年報酬%（第1欄 v8 為對照）")
ve,vd=pickle.load(open("v8_full.pkl","rb"))["eq"],[t[0] for t in pickle.load(open("v8_full.pkl","rb"))["tr"]]
v8s=pd.Series(ve[1:],index=pd.to_datetime(vd))
def yr_ret(e,y):
    try: s=e.loc[str(y)]
    except KeyError: return None
    if len(s)<5: return None
    pr=e[e.index.year==y-1]
    if len(pr)==0: return None
    return s.iloc[-1]/pr.iloc[-1]-1
names=["v8"]+[nm for nm,_ in CFG]
print("年    "+"".join(f"{n:>18}" for n in names))
tab={}
for y in range(2010,2027):
    vals=[yr_ret(v8s,y)]+[yr_ret(out[nm][0],y) for nm,_ in CFG]
    tab[y]=vals
    line=f"{y}  "+"".join(f"{(v*100 if v is not None else float('nan')):17.1f}%" for v in vals)
    print(line)
print()
print("近年合計（2023-01 ~ 2026-06）:")
for nm,ser in [("v8",v8s)]+[(nm,out[nm][0]) for nm,_ in CFG]:
    s=ser.loc["2023-01-01":]
    yy=(s.index[-1]-s.index[0]).days/365.25
    print(f"  {nm:<20} CAGR {((s.iloc[-1]/s.iloc[0])**(1/yy)-1)*100:7.1f}%")
pickle.dump(out,open("v11_final.pkl","wb"))
