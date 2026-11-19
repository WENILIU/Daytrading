# -*- coding: utf-8 -*-
import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]: os.environ[k]="1"
import sys, io, warnings, pickle, hashlib; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
import v13_target as T
from v13_engine import snap_price, CAP0, SLO
# 保守版. 基準=v21_report 真實成本冠軍(th-1.2/gap8,size2.6)。兩段式: PassA 只建 09:01 量能矩陣(純量),
#   base/cap 引擎跑; PassB 只對 cap-run 實際成交的 (code,date) 讀完整分钟K做 (b) 修正。
TH=-0.012; QMIN=0.20; GAPMAX=0.08; ZTMIN=0.014; LIQ=0.25; BRAKE=((-0.03,0.30),(-0.06,0.12)); DMIN="2023-05-23"
SS=float(sys.argv[1]) if len(sys.argv)>1 else 2.6; CAP=float(sys.argv[2]) if len(sys.argv)>2 else 0.10
ONE=r"D:\Codex\2026-11-14\new-chat-2\outputs\capital_stock_data\data\fugle_1m"
ONEF={f[:-8]:os.path.join(ONE,f) for f in os.listdir(ONE)} if os.path.isdir(ONE) else {}
os.makedirs("fill_probe",exist_ok=True)

D=T.D.copy(); D["_d"]=pd.to_datetime(D["date"])
BASE=D[(D["_d"]>=pd.Timestamp(DMIN))&(~D["blocked"].values)]
Dw=BASE[(BASE["pred_q"].fillna(-1)>=QMIN)&(BASE["price_dir"]<TH)]
ctx={}
for _,rr in Dw.iterrows():
    ctx[(str(pd.Timestamp(rr["date"]).date()),str(rr["stock"]).zfill(4),rr["direction"])]=dict(
        pr=float(rr["entry"]),lu=float(rr["lu"]),ld=float(rr["ld"]),tk=float(rr["tick"]))
need={}; 
for (d,s,side) in ctx: need.setdefault(s,set()).add(d)

# ---- Pass A: 09:01 dollar volume 矩陣(純量) ----
FVC="fill_probe/_fv_cache.pkl"; kA=hashlib.md5((",".join(sorted(need))+str(len(ctx))).encode()).hexdigest()
FV=None
if os.path.exists(FVC):
    b=pickle.load(open(FVC,"rb"))
    if b.get("k")==kA: FV=b["FV"]; print(f"PassA 快取命中: FV {len(FV.columns)}檔 x {len(FV.index)}日",flush=True)
if FV is None:
    print(f"PassA 讀 09:01 量能: {len(need)} 檔 ...",flush=True); fv={}
    for i,c in enumerate(need,1):
        p=ONEF.get(c)
        if not p: continue
        try: m=pd.read_parquet(p, columns=["time","close","volume"])
        except Exception: continue
        t=pd.to_datetime(m["time"]); mm=(t.dt.hour*60+t.dt.minute).values; dd=t.dt.normalize()
        for ds in need[c]:
            sel=((dd==pd.Timestamp(ds)).values)&(mm==541)
            if sel.any(): fv[(c,ds)]=float((m["volume"].values[sel]*1000.0*m["close"].values[sel]).sum())
        if i%300==0: print(f"  {i}/{len(need)}",flush=True)
    FV=pd.DataFrame(0.0,index=sorted({pd.Timestamp(k[1]) for k in fv}),columns=sorted({k[0] for k in fv}))
    for (c,d),v in fv.items():
        if c in FV.columns: FV.at[pd.Timestamp(d),c]=v
    pickle.dump({"k":kA,"FV":FV},open(FVC,"wb")); print(f"PassA 完成: {len(fv)} 筆 09:01 量能",flush=True)

def mk(): T.GROUPS={d:g for d,g in Dw.groupby("date")}; T.days=sorted(Dw["date"].unique())
def run(cap_on):
    mk()
    if cap_on:
        o1,ok=T.TO1,T.K_OPEN; T.TO1=FV; T.K_OPEN=1.0
        r=T.run(slip_scale=1.0,date_min=DMIN,s3=False,size_scale=SS,exposure=1.0,gap_max=GAPMAX,
                zt_min_dist=ZTMIN,liq=CAP,brake=BRAKE,capture=True); T.TO1,T.K_OPEN=o1,ok
    else:
        r=T.run(slip_scale=1.0,date_min=DMIN,s3=False,size_scale=SS,exposure=1.0,gap_max=GAPMAX,
                zt_min_dist=ZTMIN,liq=LIQ,brake=BRAKE,capture=True)
    return r

# ---- Pass B: 只對 cap-run 實際成交且有1m 的 (code,date) 读完整分钟K ----
def load_bars(pairs):
    BC="fill_probe/_bars_cache.pkl"; kB=hashlib.md5((",".join(f"{c}_{d}" for c,d in sorted(pairs))).encode()).hexdigest()
    if os.path.exists(BC):
        b=pickle.load(open(BC,"rb"))
        if b.get("k")==kB: print(f"PassB 快取命中: {len(b['B'])} bars",flush=True); return b["B"]
    B={}; byc={}
    for c,d in pairs: byc.setdefault(c,set()).add(d)
    print(f"PassB 读完整分钟K: {len(byc)} 檔/{len(pairs)} 日 ...",flush=True)
    for c,dset in byc.items():
        p=ONEF.get(c)
        if not p: continue
        try: m=pd.read_parquet(p, columns=["time","open","high","low","close","volume"])
        except Exception: continue
        t=pd.to_datetime(m["time"]); m=m.assign(_d=t.dt.normalize(),_m=(t.dt.hour*60+t.dt.minute),
            _usd=m["volume"].values*1000.0*m["close"].values).sort_values("time")
        grp={dt:g for dt,g in m.groupby("_d")}; ud=sorted(grp); pos={dt:i for i,dt in enumerate(ud)}
        for ds in dset:
            g=grp.get(pd.Timestamp(ds))
            if g is None: continue
            gm=g["_m"].values; f25=g[(gm>=804)&(gm<=805)]; i=pos[pd.Timestamp(ds)]; no=np.nan
            if i+1<len(ud):
                ng=grp[ud[i+1]]; n9=ng[ng["_m"].values==541]
                if len(n9): no=float(n9["open"].values[0])
            B[(c,ds)]=dict(o=g["open"].values,h=g["high"].values,l=g["low"].values,gm=gm,
                cl_close=float(g["close"].values[-1]),next_open=no,v132425=float(f25["_usd"].sum()) if len(f25) else 0.0)
    pickle.dump({"k":kB,"B":B},open(BC,"wb")); return B

def gap_extra(tr,B):
    dd,code,side,notional,gross,reason,pr,ex=tr
    if not str(reason).startswith("停損"): return 0.0
    c=ctx.get((dd,str(code).zfill(4),side)); b=B.get((str(code).zfill(4),dd))
    if not c or not b: return 0.0
    if side=="SHORT":
        slp=min(snap_price(pr*(1+SLO)),round(c["lu"]-c["tk"],2)); idx=np.where(b["h"]>=slp)[0]
        return (float(b["o"][idx[0]])-slp)/pr if len(idx) and b["o"][idx[0]]>slp else 0.0
    slp=max(snap_price(pr*(1-SLO)),round(c["ld"]+c["tk"],2)); idx=np.where(b["l"]<=slp)[0]
    return (slp-float(b["o"][idx[0]]))/pr if len(idx) and b["o"][idx[0]]<slp else 0.0
def cover_extra(tr,B):
    dd,code,side,notional,gross,reason,pr,ex=tr
    if str(reason)!="13:25 強制平倉": return 0.0
    b=B.get((str(code).zfill(4),dd))
    if not b or not np.isfinite(b.get("next_open",np.nan)) or not (b["v132425"]>0): return 0.0
    if notional<=CAP*b["v132425"]: return 0.0
    frac=1.0-(CAP*b["v132425"])/notional; adv=(float(b["next_open"])-b["cl_close"])/pr if side=="SHORT" else (b["cl_close"]-float(b["next_open"]))/pr
    return max(adv,0.0)*frac
def ym(r,B=None,ug=False,uc=False):
    a={}
    for tr in r["trades"]:
        y=tr[3]*tr[4]
        if ug and B: y-=tr[3]*gap_extra(tr,B)
        if uc and B: y-=tr[3]*cover_extra(tr,B)
        a[tr[0]]=a.get(tr[0],0.0)+y
    return a
def book(agg):
    ds=sorted(agg); v=[agg[k] for k in ds]; dates=pd.to_datetime(ds)
    book_=float(CAP0); peak=float(CAP0); mdd=0.0; yearly={}
    for dt,y in zip(dates,v):
        book_+=y
        if book_>CAP0: book_=CAP0
        peak=max(peak,book_); mdd=min(mdd,(book_-peak)/peak)
        yearly[dt.year]=yearly.get(dt.year,0.0)+y
    rets=[yearly[y]/CAP0*100 for y in sorted(yearly)]
    return (np.mean(rets) if rets else 0.0),mdd*100.0,100.0*np.mean([x>0 for x in v]) if v else 0.0

print("\n=== 保守版 (v21_report 真實成本冠軍 size=%.1f, 09:01 cap=%.0f%%) ==="%(SS,CAP*100),flush=True)
print("指標=逐年報酬均值(對450萬) / book路徑MDD / 獲利日%\n",flush=True)
rb=run(False); m0,d0,w0=book(ym(rb)); print("[A 現行基準(無cap)] 引擎自報 年均 %+.1f%% MDD %+.2f%% | 重建 年均 %+.1f%% MDD %+.2f%% 筆 %d"%(np.mean([rb["yearly"][k]/CAP0*100 for k in rb["yearly"]]),rb["mdd"],m0,d0,len(rb["trades"])),flush=True)
rc=run(True); pairs=sorted({(str(t[1]).zfill(4),t[0]) for t in rc["trades"]}); B=load_bars(pairs)
m1,d1,w1=book(ym(rc,B)); print("[B +cap%.0f%% 09:01量能(引擎sizing)] 年均 %+.1f%% MDD %+.2f%% 獲利日%.1f%% 筆 %d"%(CAP*100,m1,d1,w1,len(rc["trades"])),flush=True)
m2,d2,w2=book(ym(rc,B,ug=True));  print("[C B+跳空穿越停損]            年均 %+.1f%% MDD %+.2f%% 獲利日%.1f%%"%(m2,d2,w2),flush=True)
m3,d3,w3=book(ym(rc,B,uc=True));  print("[D B+13:25平不掉carry]       年均 %+.1f%% MDD %+.2f%% 獲利日%.1f%%"%(m3,d3,w3),flush=True)
m4,d4,w4=book(ym(rc,B,ug=True,uc=True)); print("[E 完整保守(B+C+D)]         年均 %+.1f%% MDD %+.2f%% 獲利日%.1f%%"%(m4,d4,w4),flush=True)
pickle.dump({"base":ym(rb),"cap":ym(rc,B),"full":ym(rc,B,True,True)},open("_conserv_out.pkl","wb")); print("\n寫入 _conserv_out.pkl",flush=True)
