import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]: os.environ[k]="1"
import sys, io, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

ONE = r"D:\Codex\2026-11-14\new-chat-2\outputs\capital_stock_data\data\fugle_1m"
files = {f[:-8]: os.path.join(ONE,f) for f in os.listdir(ONE)}
CAP0 = T.CAP0
csv = glob.glob("v21_trades_*cons.csv")[0]
d = pd.read_csv(csv, encoding="utf-8-sig")
c = d.columns.tolist()
# positional map: 0 date,1 stock,2 dir,8 lots,9 notional,10 backtest_entry,11 backtest_exit,12 reason,13 net_pct,14 net_yuan
d = d.rename(columns={c[i]:nm for i,nm in enumerate(
    ["date","stock","dir","rank","gap","pdir","zdist","predq","lots","notional","bentry","bexit","reason","bnetpct","bnet","rf0901","rx","rreason","rnetpct","rnet"][:len(c)],
    )}) if len(c)<=20 else d
d["code"] = d["stock"].astype(str).str.zfill(4)
print("loaded trades:", len(d), flush=True)

# lock status from signals (no 1m needed)
LK = T.D.copy(); LK["code"]=LK["stock"].astype(str).str.zfill(4); LK["dts"]=pd.to_datetime(LK["date"]).dt.strftime("%Y-%m-%d")
Lmap = { (r["dts"], r["code"]): (float(r["lu"]), float(r["ld"]), float(r["day_close"]), r["direction"]) for _,r in LK.iterrows() }

def is_locked(row):
    k = (str(row["date"])[:10], row["code"])
    if k not in Lmap: return False, None
    lu, ld, cl, dirn = Lmap[k]
    if dirn=="SHORT": return (cl >= lu-1e-6), lu
    else: return (cl <= ld+1e-6), ld
d["locked"]=[is_locked(r)[0] for _,r in d.iterrows()]
d["lu_ld"]=[is_locked(r)[1] for _,r in d.iterrows()]

# read 1m once for all trades: get today late vol (13:00-25 shares), today open, and NEXT-day open price
RES = {}
need = {}
for _,r in d.iterrows(): need.setdefault(r["code"], set()).add(str(pd.Timestamp(r["date"]).date()))
print("files needed:", len(need), flush=True)
n=0
for cde, dset in need.items():
    n+=1
    if n%300==0: print("  ...%d/%d"%(n,len(need)), flush=True)
    p=files.get(cde)
    if not p: continue
    try: m=pd.read_parquet(p, columns=["time","open","volume"])
    except Exception: continue
    t=pd.to_datetime(m["time"]); mm=(t.dt.hour*60+t.dt.minute).values; dd=t.dt.normalize()
    op=m["open"].values; vol=m["volume"].values*1000.0
    days=sorted(pd.unique(dd)); pos={u:i for i,u in enumerate(days)}
    byd={u:(dd.values==u) for u in days}
    for ds in dset:
        u=np.datetime64(ds)
        if u not in pos: continue
        mk=byd[u]; mi=mm[mk]; vs=vol[mk]
        late=float(vs[(mi>=780)&(mi<=805)].sum())
        openv=float(vs[mi==541].sum())
        nxt=np.nan
        i=pos[u]
        if i+1 < len(days):
            nx=days[i+1]; mn=byd[nx]; on=op[mn]; mnv=mm[mn]
            sel=mnv>=540
            if sel.any(): nxt=float(on[sel][0])
        RES[(cde,ds)]=(late,openv,nxt)
print("1m done. RES:", len(RES), flush=True)

rows=[]
for _,r in d.iterrows():
    ds=str(pd.Timestamp(r["date"]).date())
    rec=RES.get((r["code"],ds))
    if rec is None: continue
    late,openv,nxt=rec
    possh = float(r["bentry"]) and (float(r["notional"])/float(r["bentry"])) or 0.0
    frac = min(1.0,(0.10*late/possh)) if possh>0 else 1.0
    residue = (1.0-frac) > 0.01
    rows.append(dict(code=r["code"],date=ds,dirn=r["dir"],notional=float(r["notional"]),bexit=float(r["bexit"]),
        bnet=float(r["bnet"]),year=int(pd.Timestamp(r["date"]).year),residue=residue,locked=bool(r["locked"]),nxt=nxt))
R=pd.DataFrame(rows)
print("")
print("total trades matched:", len(R), " notional 10k:", round(R['notional'].sum()/1e4,1), flush=True)
res=R[R["residue"]]
print("RESIDUE (cannot fully close at 13:00, cap10): trades=%d notional10k=%.1f (%.2f%% of book notional)" %
      (len(res), res['notional'].sum()/1e4, res['notional'].sum()/R['notional'].sum()*100), flush=True)
print("  of which LOCKED at price limit: %d (%.1f%% of residue trades, %.1f%% of residue notional)" %
      (res['locked'].sum(), res['locked'].mean()*100, res[res['locked']]['notional'].sum()/max(1,res['notional'].sum())*100), flush=True)
nl=res[~res["locked"]]
print("  of which thin-but-TRADEABLE (not locked): %d, notional10k=%.1f" % (len(nl), nl['notional'].sum()/1e4), flush=True)

# carry to next-day open for NON-LOCKED residue (the hidden optimism the headline ignores)
sgn = np.where(nl["dirn"]=="LONG",1.0,-1.0)
valid = nl["nxt"].notna() & (nl["nxt"]>0) & (nl["bexit"]>0)
addl = sgn[valid.values]*((nl["nxt"][valid]-nl["bexit"][valid])/nl["bexit"][valid])
carry_yuan = addl*nl["notional"][valid]
print("  NON-LOCKED carry: n=%d avg=%+.3f%%/trade total=%+.1f 10k  (SHORT %d, LONG %d)" %
      (int(valid.sum()), addl.mean()*100, carry_yuan.sum()/1e4,
       int((nl['dirn'][valid]=="SHORT").sum()), int((nl['dirn'][valid]=="LONG").sum())), flush=True)
byyear = pd.Series(carry_yuan.values).groupby(nl["year"][valid].values).sum()
pp = {y: byyear[y]/CAP0*100 for y in byyear.index}
print("  annual drag if held to next open (%% of CAP0):", {str(y): round(v,2) for y,v in pp.items()}, flush=True)
print("  AVG annual drag = %+.2f pp  ->  fully-honest headline ~ %+.1f%%" %
      (-np.mean(list(pp.values())), 147.4 + np.mean(list(pp.values()))), flush=True)

# sanity: measured next-open cost for LOCKED shorts (engine charges ps=-3.149%)
ls = res[(res["locked"]) & (res["dirn"]=="SHORT") & res["nxt"].notna()]
if len(ls):
    # engine assumed exit at limit price lu; true buyback at next open: short ret=(lu-next)/lu
    true = (ls["lu_ld"].astype(float) if "lu_ld" in ls else np.nan)
    pass
print("DONE", flush=True)
