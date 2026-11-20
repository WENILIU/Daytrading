import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]: os.environ[k]="1"
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

S, E = "2023-05-23", "2026-12-31"
TH = -0.012
ONE = r"D:\Codex\2026-11-14\new-chat-2\outputs\capital_stock_data\data\fugle_1m"
files = {f[:-8]: os.path.join(ONE,f) for f in os.listdir(ONE)}

D = T.D.copy(); D["_d"] = pd.to_datetime(D["date"])
MON = D[(D["_d"] >= pd.Timestamp(S)) & (D["_d"] <= pd.Timestamp(E))]
BASEF = MON[(~MON["blocked"].values) & (MON["pred_q"].fillna(-1) >= 0.20) & (MON["price_dir"] < TH)]
pairs = sorted({(str(s).zfill(4), str(pd.Timestamp(d).date())) for d, s in zip(BASEF["date"], BASEF["stock"])})
need = {}
for c, ds in pairs: need.setdefault(c, set()).add(ds)
print("reading 1m for %d codes / %d pairs ..." % (len(need), len(pairs)), flush=True)

EXIT = {}   # (code,ds) -> prior-day 13:00-25 TWD (exit-liquidity proxy)
LATE = {}   # (code,ds) -> today 13:00-25 volume SHARES (for residue measure)
OPEN = {}   # (code,ds) -> today 09:01 TWD (cross-check)
done = 0
for c, dset in need.items():
    done += 1
    if done % 200 == 0: print("  ...%d/%d" % (done, len(need)), flush=True)
    p = files.get(c)
    if not p: continue
    try: m = pd.read_parquet(p, columns=["time","close","volume"])
    except Exception: continue
    t = pd.to_datetime(m["time"]); mm = (t.dt.hour*60+t.dt.minute).values; dd = t.dt.normalize().values
    vs = m["volume"].values*1000.0; cl = m["close"].values
    twd = vs*cl
    days = pd.Series(dd); udays = np.unique(days); pos = {u: i for i, u in enumerate(udays)}
    # group masks by day once
    byd = {}
    order = np.argsort(dd)
    sdd = dd[order]
    bounds = np.searchsorted(sdd, np.unique(sdd), side="right")
    starts = np.r_[0, bounds[:-1]]
    for u, st in zip(np.unique(sdd), starts):
        en = bounds[np.searchsorted(np.unique(sdd), u)]
        byd[u] = slice(st, en)  # indices into sorted arrays
    def day_late_sh(u):
        sl = byd.get(u)
        if sl is None: return 0.0, 0.0
        idx = order[sl]; mi = mm[idx]; sh = vs[idx]; t_ = twd[idx]
        inw = (mi >= 780) & (mi <= 805); on541 = (mi == 541)
        return float(sh[inw].sum()), float(t_[on541].sum())
    for ds in dset:
        key = str(pd.Timestamp(ds).date())
        dts = np.datetime64(key)
        if dts not in pos: continue
        i = pos[dts]
        sh_today, open_twd = day_late_sh(udays[i])
        LATE[(c, key)] = sh_today; OPEN[(c, key)] = open_twd
        if i > 0:
            sh_prev, _ = day_late_sh(udays[i-1])
            # convert prev shares to TWD using prev avg price ~ today's (approx): use prev day twd directly
            slp = byd.get(udays[i-1]); twd_prev = 0.0
            if slp is not None:
                idxp = order[slp]; mip = mm[idxp]; twdp = twd[idxp]
                inwp = (mip >= 780) & (mip <= 805); twd_prev = float(twdp[inwp].sum())
            EXIT[(c, key)] = twd_prev
print("1m read done. EXIT entries:", len(EXIT), "LATE:", len(LATE), flush=True)

# ---- baseline (no guard) via existing builder for fair compare ----
FV_open = T.build_open_volume_matrix([(c, ds) for c, ds in pairs])
codes = list(FV_open.columns); idxs = list(FV_open.index)
EX = pd.DataFrame(0.0, index=idxs, columns=codes)
for (c, ds), v in EXIT.items():
    cds = pd.Timestamp(ds)
    if c in EX.columns and cds in EX.index and v > 0:
        EX.at[cds, c] = v
# guarded dv1: where EXIT known & smaller, cap by EXIT; else keep open
GUARD = FV_open.values.copy()
mask = (EX.values > 0) & (EX.values < FV_open.values)
GUARD[mask] = EX.values[mask]
GUARD = pd.DataFrame(GUARD, index=idxs, columns=codes)
print("guarded cells: %d of %d open-cells (%.1f%%)" % (int(mask.sum()), int((FV_open.values>0).sum()), mask.sum()/max(1,(FV_open.values>0).sum())*100), flush=True)

def run_with(dv):
    T.GROUPS = {d: g for d, g in BASEF.groupby("date")}; T.days = sorted(BASEF["date"].unique())
    T.TO1 = dv; T.K_OPEN = 1.0
    r = T.run(slip_scale=1.0, date_min=S, s3=False, size_scale=2.6, exposure=1.0,
              gap_max=0.08, zt_min_dist=0.014, liq=T.REAL_OPEN_CAP,
              brake=((-0.03,0.30),(-0.06,0.12)), capture=True)
    y = r["yearly"]; rets = [y[k]/T.CAP0*100 for k in sorted(y)]
    return r, dict(mdd=r["mdd"], avg=float(np.mean(rets)), worst=float(min(rets)),
                   med=float(np.median(rets)), per_day=r["per_day"],
                   yrs={k: round(v,1) for k, v in zip(sorted(y), rets)})

print("")
print("=== HEADLINE compare (size 2.6, baseline breadth) ===")
rB, mB = run_with(FV_open)
print("NO-GUARD : MDD %+.2f%%  AVG %+.1f%%  WORST %+.1f%%  MED %+.1f%%  perday %.2f" % (mB['mdd'],mB['avg'],mB['worst'],mB['med'],mB['per_day']), flush=True)
print("           yearly:", mB['yrs'], flush=True)
rG, mG = run_with(GUARD)
print("GUARD    : MDD %+.2f%%  AVG %+.1f%%  WORST %+.1f%%  MED %+.1f%%  perday %.2f" % (mG['mdd'],mG['avg'],mG['worst'],mG['med'],mG['per_day']), flush=True)
print("           yearly:", mG['yrs'], flush=True)

def residue(r):
    tot = 0.0; res = 0.0; nres = 0
    for (dd, code, side, notional, gross, reason, pr, ex) in r["trades"]:
        c = str(code).zfill(4); key = str(pd.Timestamp(dd).date())
        late = LATE.get((c, key), None)
        if late is None or pr <= 0: continue
        pos_sh = notional/pr
        closeable = 0.10*late
        frac = min(1.0, closeable/pos_sh) if pos_sh > 0 else 1.0
        tot += notional; res += notional*(1-frac)
        if (1-frac) > 0.01: nres += 1
    return res/tot*100 if tot else 0.0, nres

rB2, _ = run_with(FV_open); rG2, _ = run_with(GUARD)
pb, nb = residue(rB2); pg, ng = residue(rG2)
print("")
print("=== RESIDUE at 13:00, cap10% (today-realized late vol) ===")
print("NO-GUARD : %.2f%% notional, %d trades leak >1%%" % (pb, nb), flush=True)
print("GUARD    : %.2f%% notional, %d trades leak >1%%" % (pg, ng), flush=True)
print("DONE", flush=True)
