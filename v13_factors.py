import pandas as pd, numpy as np, pickle, os, time, warnings; warnings.filterwarnings("ignore")
FINLAB=r"D:\AI專案\StockAgent\finlab\database"   # seed only, read once, never written
STORE=r"D:\gapfade_data"                           # our own price store (see refresh_prices)
PANEL=r"D:\gapfade_data\zt_factors.pkl"
CACHE=r"D:\gapfade_data\zt_turnover.pkl"
LATEST=r"D:\gapfade_data\zt_latest.pkl"   # tiny: last row of every factor + turnover
PKL=["close","open","high","low","vol"]
# finlab 2.x dataset names. price:vol does NOT exist - volume is price:成交股數.
DS={"close":"price:close","open":"price:open","high":"price:high","low":"price:low",
    "vol":"price:成交股數"}
FINLAB_TOKEN=os.environ.get("GAPFADE_FINLAB_TOKEN",
    "Vww04G2yj5qcHkqX6yNCKIOw/GE2oJ9dIlFftXoeN3NqjQTv0YAqWujox5k/ilKd#vip_m")


def _sp(k):
    return os.path.join(STORE, f"price_{k}.pkl")


def seed_store():
    """One-time copy of the 1.x finlab pkl files into our own store.

    We keep a private copy because appending a tail (and re-deriving the last
    row) must not mutate a data set other projects read.
    """
    os.makedirs(STORE, exist_ok=True)
    for k in PKL:
        if not os.path.exists(_sp(k)):
            t=time.time()
            df=pd.read_pickle(os.path.join(FINLAB, f"price_{k}.pkl")).astype(float)
            df.to_pickle(_sp(k))
            print(f"[seed] price_{k}.pkl {df.shape} in {time.time()-t:.0f}s")


def refresh_prices(overlap=10, end=None):
    """Download the missing tail from finlab (VIP) and append it to our store.

    The last `overlap` rows are RE-DOWNLOADED and overwritten rather than
    skipped: the local copy was snapshotted at 16:23 on 2026-08-19, before
    after-hours settled, so its final row understates volume on 45 names
    (2330 by 1.77%, 2383 by 5.23%). Re-deriving a window self-heals that.

    Returns the store's last date.
    """
    import finlab, finlab.data as D
    finlab.login(FINLAB_TOKEN)
    out={}; last=None
    for k in PKL:
        path=_sp(k)
        cur=pd.read_pickle(path).astype(float) if os.path.exists(path) else None
        if cur is None:
            raise RuntimeError(f"store missing {path}; run seed_store() first")
        start=pd.Timestamp(cur.index.max()) - pd.Timedelta(days=overlap)
        new=D.get(DS[k], start=start.strftime("%Y-%m-%d"),
                  end=end or pd.Timestamp.today().strftime("%Y-%m-%d"),
                  save_to_storage=False)
        new=new.astype(float)
        if new.index.max() <= cur.index.max():
            out[k]=cur; last=cur.index.max(); continue
        cols=cur.columns.union(new.columns, sort=False)
        base=cur.reindex(columns=cols)
        # overwrite the overlap window with the authoritative values, then append
        keep=[d for d in base.index if d < start]
        upd=pd.concat([base.loc[keep], new.reindex(columns=cols)])
        upd=upd[~upd.index.duplicated(keep="last")].sort_index()
        upd=upd.astype(float)
        out[k]=upd; last=upd.index.max()
        print(f"[refresh] price_{k:5s} {cur.shape[0]} -> {upd.shape[0]} rows "
              f"(cols {len(cur.columns)} -> {len(cols)}), last {last.date()}")
    for k in PKL:
        out[k].to_pickle(_sp(k))
    return last
ZF=["lock_rate_up_250","touch_rate_up_250","lock_rate_dn_250","touch_rate_dn_250",
    "lock_rate_up_500","touch_rate_up_500","lock_rate_dn_500","touch_rate_dn_500",
    "zt_close_20","zt_close_60","gapup_60","gapdn_60","vol_ratio","ret_20","dist_hi60","price"]

def build():
    """Derive the factor panel from our own price store (see refresh_prices)."""
    C=pd.read_pickle(_sp("close")).astype(float)
    H=pd.read_pickle(_sp("high")).astype(float)
    L=pd.read_pickle(_sp("low")).astype(float)
    O=pd.read_pickle(_sp("open")).astype(float)
    V=pd.read_pickle(_sp("vol")).astype(float)
    PC=C.shift(1); valid=PC.notna()&(PC>0)
    tick=pd.DataFrame(np.select([PC.values<10,PC.values<100,PC.values<500,PC.values<1000,PC.values<5000],
            [0.05,0.1,0.5,1.0,5.0],10.0),index=PC.index,columns=PC.columns)
    LU=pd.DataFrame(np.floor(PC.values*1.10/tick.values)*tick.values,index=PC.index,columns=PC.columns)
    LD=pd.DataFrame(np.ceil(PC.values*0.90/tick.values)*tick.values,index=PC.index,columns=PC.columns)
    up_t=(H.values>=LU.values-1e-9)&valid.values; up_l=(C.values>=LU.values-1e-9)&valid.values
    dn_t=(L.values<=LD.values+1e-9)&valid.values; dn_l=(C.values<=LD.values+1e-9)&valid.values
    gu=(O.values>=PC.values*1.05)&valid.values; gd=(O.values<=PC.values*0.95)&valid.values
    idx,cols=C.index,C.columns
    def mk(a): return pd.DataFrame(np.asarray(a,dtype=float),index=idx,columns=cols)
    def rate(n,d,win,mind):
        a=mk(n).rolling(win).sum(); b=mk(d).rolling(win).sum(); return (a/b).where(b>=mind)
    f={}
    for w,md in [(250,3),(500,5)]:
        f[f"lock_rate_up_{w}"]=rate(up_t,up_t,w,md); f[f"touch_rate_up_{w}"]=rate(up_t&gu,gu,w,md)
        f[f"lock_rate_dn_{w}"]=rate(dn_t,dn_t,w,md); f[f"touch_rate_dn_{w}"]=rate(dn_t&gd,gd,w,md)
    f["zt_close_20"]=mk(up_l).rolling(20).sum(); f["zt_close_60"]=mk(up_l).rolling(60).sum()
    f["gapup_60"]=mk(gu).rolling(60).sum(); f["gapdn_60"]=mk(gd).rolling(60).sum()
    f["vol_ratio"]=V/V.rolling(20).mean(); f["ret_20"]=C/C.shift(20)-1
    f["dist_hi60"]=C/C.rolling(60).max()-1; f["price"]=C
    for k in list(f): f[k]=f[k].shift(1)
    tv=(V*C).shift(1)
    os.makedirs(os.path.dirname(PANEL),exist_ok=True)
    pickle.dump(f,open(PANEL,"wb")); pickle.dump(tv,open(CACHE,"wb"))
    write_latest(f,tv)
    return f,tv


def write_latest(f,tv):
    """Persist ONLY the last row (what the live trader needs). ~200KB instead of 1.7GB."""
    lat={"date":str(f["price"].index.max())}
    for k,v in f.items(): lat[k]=v.iloc[-1]
    if tv is not None: lat["turnover"]=tv.iloc[-1]
    pickle.dump(lat,open(LATEST,"wb"))
    return lat


def latest(force=False):
    """Live path: load the tiny latest-row cache. Falls back to the big panel."""
    if not force and os.path.exists(LATEST):
        lat=pickle.load(open(LATEST,"rb"))
        tv=lat.pop("turnover",None)
        return pd.DataFrame({k:v for k,v in lat.items() if k!="date"}), tv, pd.Timestamp(lat["date"])
    f,tv=load(); lat=write_latest(f,tv)
    tv=lat.pop("turnover",None)
    return pd.DataFrame({k:v for k,v in lat.items() if k!="date"}), tv, pd.Timestamp(lat["date"])

def load(force=False):
    if force or not os.path.exists(PANEL):
        t=time.time(); f,tv=build(); print(f"[factors] rebuilt from finlab in {time.time()-t:.0f}s"); return f,tv
    f=pickle.load(open(PANEL,"rb")); tv=pd.read_pickle(CACHE) if os.path.exists(CACHE) else None
    return f,tv

def asof_row(f,tv,asof):
    """Return (factor_row_df, turnover_row_series, panel_last_date) for the last date <= asof."""
    a=pd.Timestamp(asof)
    idx=f["price"].index; got=idx[idx<=a]
    if len(got)==0: return None,None,None
    d=got[-1]
    return pd.DataFrame({k:v.loc[d] for k,v in f.items()}), (None if tv is None else tv.loc[d]), d

if __name__=="__main__":
    import sys
    if "--seed" in sys.argv:
        seed_store(); sys.exit(0)
    if "--refresh" in sys.argv:
        t=time.time()
        seed_store()
        d=refresh_prices()
        print(f"[refresh] price store now ends {d}")
        f,tv=build(); write_latest(f,tv)
        print(f"refreshed panel+turnover+latest in {time.time()-t:.0f}s")
        print(f"[refresh] panel ends {f['price'].index.max()} "
              f"({f['price'].shape[0]} rows x {f['price'].shape[1]} cols)")
        sys.exit(0)
    R,T,d=latest()
    print("LATEST cache: date",d,"stocks",R.shape[1],"turnover keys",0 if T is None else int(T.notna().sum()))
    f,tv=load()
    print("panel last date:",f["price"].index.max(),"stocks:",f["price"].shape[1])
    print("turnover panel:",None if tv is None else (tv.index.max(),tv.shape))
    R,T,d=asof_row(f,tv,"2026-10-26")
    print("asof used:",d,"cols:",list(R.columns)[:6],"...")
    print("sample 2330:",{k:(None if pd.isna(R.loc[d,'2330'] if False else R.loc['2330',k]) else round(float(R.loc['2330',k]),4)) for k in ZF[:6]})
    if T is not None: print("T-1 turnover 2330:",None if pd.isna(T.get('2330')) else float(T.get('2330')))
