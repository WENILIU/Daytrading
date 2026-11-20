import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]: os.environ[k]="1"
import sys, io, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

ONE = r"D:\Codex\2026-11-14\new-chat-2\outputs\capital_stock_data\data\fugle_1m"
files = {f[:-8]: os.path.join(ONE,f) for f in os.listdir(ONE)}
csv = glob.glob("v21_trades_*cons.csv")[0]
d = pd.read_csv(csv, encoding="utf-8-sig")
d = d.iloc[:, [0,1,8,9,15]].rename(columns=lambda x: x)
d.columns = ["date","stock","lots","notional","entry"]
d = d[d["lots"].fillna(0) > 0].copy()
d["code"] = d["stock"].astype(str).str.zfill(4)
d["pos_sh"] = d["lots"].astype(float)*1000.0
print("trades with lots:", len(d), "total notional 10k:", round(d['notional'].sum()/1e4,1), flush=True)

# minute index: 540=09:00 .. 805=13:25
STARTS = {"13:25":805, "13:00":780, "12:00":720, "11:00":660, "10:30":630, "10:00":600}
CAPS = [0.10, 0.20, 0.30]
rows=[]
cache={}
for _,r in d.iterrows():
    c=r["code"]; ds=r["date"]
    if c not in cache:
        p=files.get(c)
        if not p: cache[c]=None; continue
        try: m=pd.read_parquet(p, columns=["time","volume"])
        except Exception: cache[c]=None; continue
        t=pd.to_datetime(m["time"]); mm=(t.dt.hour*60+t.dt.minute).values; dd=t.dt.normalize()
        cache[c]=(mm, dd.values, (m["volume"].values*1000.0))  # vol shares
    v=cache[c]
    if v is None: continue
    mm, dd, vol = v
    sel = (dd == pd.Timestamp(ds).to_datetime64())
    idx = mm[sel]; vs = vol[sel]
    if len(idx)==0: continue
    volmap = pd.Series(vs, index=idx).groupby(level=0).sum()
    openv = float(volmap.get(541, 0.0))
    rec = {"date":ds,"code":c,"notional":float(r["notional"]),"pos":float(r["pos_sh"]),"openv":openv}
    for nm,st in STARTS.items():
        fillv = float(volmap[(volmap.index>=st)&(volmap.index<=805)].sum())  # sum vol shares in window
        rec["latev_"+nm] = fillv
        rec["ratio_"+nm] = (fillv/openv) if openv>0 else np.nan
    rows.append(rec)
R=pd.DataFrame(rows)
print("matched:", len(R), flush=True)

def resid(cap, start):
    # position sized ~ 0.10*openv; closeable = cap/cap0 * latev ; use notional-weighted residue
    cap0=0.10
    pos_n = R["notional"]
    closeable_share = (cap* R["latev_"+start]) / (cap0*R["openv"])  # TWD ratio late vs sizing basis
    frac = np.clip(closeable_share, 0, 1)
    res = (pos_n*(1-frac)).sum()/pos_n.sum()*100
    return res

print("")
print("OVERNIGHT RESIDUE %% (notional-weighted) by start time x participation cap")
print("%-10s %10s %10s %10s" % ("start","cap10%","cap20%","cap30%"))
for nm in ["13:25","13:00","12:00","11:00","10:30","10:00"]:
    print("%-10s %10.1f %10.1f %10.1f" % (nm, resid(0.10,nm), resid(0.20,nm), resid(0.30,nm)), flush=True)

print("")
print("DIAGNOSTIC: late-window vol / 09:01 open-min vol (the ratio that decides closeability)")
for nm in ["13:25","13:00","12:00","11:00"]:
    s=R["ratio_"+nm].replace([np.inf,-np.inf],np.nan).dropna()
    print("  start %s: median late/open = %s | frac<1.0 (cannot fully unwind) = %.1f%%" %
          (nm, ("%s"%np.round(np.median(s),2)), (s<1.0).mean()*100), flush=True)

print("")
print("CONCENTRATION at cap10/start13:00: who holds the residue")
cap=0.10; start="13:00"
closeable=(cap*R["latev_"+start])/(0.10*R["openv"])
R["res"]=(R["notional"]*(1-np.clip(closeable,0,1)))
tot=R["res"].sum()
R=R.sort_values("res",ascending=False).reset_index(drop=True)
print("  total residue 10k: %.1f | trades >1pct-left: %d" % (tot/1e4, int((R["res"]>0.01*R["notional"]).sum())))
for sh in [0.10,0.25,0.50,1.0]:
    k=int(np.ceil(sh*len(R)))
    print("  top %3d%% of trades (%d) = %.0f%% of total residue" % (sh*100,k,R["res"].head(k).sum()/tot*100), flush=True)
print("")
print("TOP 10 residue trades (date code openV_sh lateV(13:00-25)_sh ratio notional10k):")
for _,x in R.head(10).iterrows():
    print("  %s %s openV=%.0f lateV=%.0f ratio=%s notional=%.0f 10k" %
          (x['date'],x['code'],x['openv'],x['latev_13:00'],np.round(x['ratio_13:00'],2),x['notional']/1e4), flush=True)
print("DONE", flush=True)
