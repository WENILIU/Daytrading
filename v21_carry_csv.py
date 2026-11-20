import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]: os.environ[k]="1"
import sys, io, glob, pickle
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

S, E = "2023-05-23", "2026-12-31"
CAP0 = float(T.CAP0)
ONE = r"D:\Codex\2026-11-14\new-chat-2\outputs\capital_stock_data\data\fugle_1m"
files = {f[:-8]: os.path.join(ONE, f) for f in os.listdir(ONE)}
src = glob.glob("v21_trades_*cons.csv")[0]
raw = pd.read_csv(src, encoding="utf-8-sig")
NAMES = ["日期","股票","方向","模型排名","跳空pct","衰竭pct","距限制pct","pred_q","張數","名義額",
         "回測進場價","回測出場價","回測出場原因","回測淨pct","回測淨額元","真實進場價0901",
         "真實出場價","真實出場原因","真實淨pct","真實淨額元"]
d = raw.iloc[:, :len(NAMES)].copy(); d.columns = NAMES
d["code"] = d["股票"].astype(str).str.zfill(4)
d["_year"] = pd.to_datetime(d["日期"]).dt.year
d = d.reset_index(drop=True)
force = d["回測出場原因"].astype(str).str.contains("13:25").values
print("loaded", len(d), "force-close", int(force.sum()), flush=True)

LK = T.D.copy(); LK["code"]=LK["stock"].astype(str).str.zfill(4)
LK["k"]=pd.to_datetime(LK["date"]).dt.strftime("%Y-%m-%d")+"|"+LK["code"]
Lmap={}
for _,r in LK.iterrows():
    Lmap[r["k"]]=(float(r["lu"]),float(r["ld"]),float(r["day_close"]),r["direction"])
def is_locked(i):
    k=str(pd.Timestamp(d.at[i,"日期"]).date())+"|"+d.at[i,"code"]
    if k not in Lmap: return False
    lu,ld,cl,dirn=Lmap[k]
    return (cl>=lu-1e-6) if dirn=="SHORT" else (cl<=ld+1e-6)

CACHE="_carry_res.pkl"
need={}
for i in np.where(force)[0]: need.setdefault(d.at[i,"code"],set()).add(str(pd.Timestamp(d.at[i,"日期"]).date()))
RES=None
if os.path.exists(CACHE):
    try:
        b=pickle.load(open(CACHE,"rb"))
        if b.get("k")==str(sorted((c,tuple(sorted(v))) for c,v in need.items())): RES=b["r"]
    except Exception: RES=None
if RES is None:
    RES={}; n=0
    for cde,dset in need.items():
        n+=1
        if n%300==0: print("  ...%d/%d"%(n,len(need)),flush=True)
        p=files.get(cde)
        if not p: continue
        try: m=pd.read_parquet(p, columns=["time","open","volume"])
        except Exception: continue
        t=pd.to_datetime(m["time"]); mm=(t.dt.hour*60+t.dt.minute).values; dd=t.dt.normalize().values
        op=m["open"].values; vol=m["volume"].values*1000.0
        days=sorted(pd.unique(dd)); pos={u:ii for ii,u in enumerate(days)}
        byd={u:(dd==u) for u in days}
        for ds in dset:
            u=np.datetime64(ds)
            if u not in pos: continue
            mk=byd[u]; mi=mm[mk]; vs=vol[mk]
            late=float(vs[(mi>=780)&(mi<=805)].sum())
            nxt=np.nan; j=pos[u]
            if j+1<len(days):
                nx=days[j+1]; mn=byd[nx]; mnv=mm[mn]; sel=mnv>=540
                if sel.any(): nxt=float(op[mn][sel][0])
            RES[(cde,ds)]=(late,nxt)
    pickle.dump({"k":str(sorted((c,tuple(sorted(v))) for c,v in need.items())),"r":RES}, open(CACHE,"wb"))
print("RES ready", len(RES), flush=True)

n=len(d)
cp=[None]*n; creason=list(d["回測出場原因"].astype(object)); cnp=list(map(float,d["回測淨pct"])); cna=list(map(float,d["回測淨額元"]))
isc=[False]*n; isl=[False]*n; isres=[False]*n
for i in np.where(force)[0]:
    lk=is_locked(i); isl[i]=lk
    rec=RES.get((d.at[i,"code"], str(pd.Timestamp(d.at[i,"日期"]).date())))
    if rec is None: continue
    late,nxt=rec
    be=d.at[i,"回測進場價"]; notl=float(d.at[i,"名義額"])
    if not (np.isfinite(float(be)) and float(be)>0 and notl>0): continue
    possh=notl/float(be); frac=min(1.0,(0.10*late/possh)) if possh>0 else 1.0
    r=(1.0-frac)>0.01; isres[i]=r
    if r and (not lk) and np.isfinite(nxt) and nxt>0:
        bex=float(d.at[i,"回測出場價"])
        if np.isfinite(bex) and bex>0:
            sgn=1.0 if d.at[i,"方向"]=="LONG" else -1.0
            newp=cnp[i]+sgn*(nxt-bex)/bex*100.0
            isc[i]=True; cp[i]=round(float(nxt),3)
            creason[i]="隔日開盤平(最壞carry)"; cnp[i]=round(newp,3)
            cna[i]=round(float(d.at[i,"名義額"])*newp/100.0)
d["最壞carry"]=isc; d["is_residue"]=isres; d["is_locked"]=isl
d["最壞carry出場價"]=pd.array([("" if v is None else v) for v in cp], dtype=object)
d["最壞carry原因"]=creason; d["最壞carry淨pct"]=cnp; d["最壞carry淨額元"]=cna

print("force", int(force.sum()), "residue", sum(isres), "locked", sum(isl), "carried", sum(isc), flush=True)
def ann(col):
    y=d.groupby("_year")[col].sum()/CAP0*100
    return float(np.mean(y.values)), {int(a):round(v,1) for a,v in y.items()}
ab,yb=ann("回測淨額元"); ac,yc=ann("最壞carry淨額元")
print("HEADLINE 回測      : AVG %+.1f%% yearly %s"%(ab,yb),flush=True)
print("HEADLINE 最壞carry : AVG %+.1f%% yearly %s"%(ac,yc),flush=True)
print("DIFF = %+.2f pp"%(ac-ab),flush=True)
book=CAP0;peak=CAP0;worst=0.0
for v in d.groupby("日期")["最壞carry淨額元"].sum().sort_index().values:
    book+=v
    if book>CAP0: book=CAP0
    peak=max(peak,book); dd=(book-peak)/peak; worst=min(worst,dd)
print("最壞carry MDD(近似) %+.2f%%"%(worst*100),flush=True)

tag="%s_%s_size2.6_carry"%(S,E)
tp=r"v21_trades_%s.csv"%tag; d.drop(columns=["code","_year"]).to_csv(tp,index=False,encoding="utf-8-sig")
gg=d.groupby("日期")
day=[]
for dt,g in gg:
    day.append(dict(日期=str(pd.Timestamp(dt).date()),筆數=len(g),
        回測淨額元=round(g["回測淨額元"].sum()),最壞carry淨額元=round(g["最壞carry淨額元"].sum()),
        回測日pct=round(g["回測淨額元"].sum()/CAP0*100,3),最壞carry日pct=round(g["最壞carry淨額元"].sum()/CAP0*100,3)))
dp=pd.DataFrame(day).sort_values("日期"); dpath=r"v21_daily_%s.csv"%tag; dp.to_csv(dpath,index=False,encoding="utf-8-sig")
yy=d.groupby("_year")[["回測淨額元","最壞carry淨額元"]].sum()
yyp=pd.DataFrame({"年份":yy.index,"回測淨額元":yy["回測淨額元"].values,"最壞carry淨額元":yy["最壞carry淨額元"].values,
    "回測年pct":(yy["回測淨額元"]/CAP0*100).round(2).values,"最壞carry年pct":(yy["最壞carry淨額元"]/CAP0*100).round(2).values})
ypath=r"v21_yearly_%s.csv"%tag; yyp.to_csv(ypath,index=False,encoding="utf-8-sig")
print("WROTE",tp); print("WROTE",dpath); print("WROTE",ypath); print("DONE",flush=True)
