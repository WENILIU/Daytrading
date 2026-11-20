# -*- coding: utf-8 -*-
import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]: os.environ[k]="1"
import sys, io, warnings, pickle, hashlib; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
# 評估「平倉開始時間 T」: 把 13:25 一次平 -> 改成從 T 起在 [T,13:25] 分散平(10% 累積量能上限,
#   成交約等於該窗 VWAP), 平不掉的剩餘才到隔天開盤。目標: 殘留(過夜)趨近 0 且成本最小。
# 只針對引擎判定 "13:25 強制平倉" 的單(這些才需要平倉決策; 停損/停利單盤中已出)。
TRADES = r"v21_trades_2023-05-23_2026-12-31_size2.6_cons.csv"
CAP = 0.10
ONE = r"D:\Codex\2026-11-14\new-chat-2\outputs\capital_stock_data\data\fugle_1m"
ONEF = {f[:-8]: os.path.join(ONE, f) for f in os.listdir(ONE)} if os.path.isdir(ONE) else {}
t = pd.read_csv(TRADES, dtype={"股票": str}); t.columns=[c.strip() for c in t.columns]
fc = t[t["回測出場原因"].astype(str) == "13:25 強制平倉"].copy()
alln = len(t); print(f"全部 {alln} 筆；其中 13:25 強制平倉 {len(fc)} 筆({len(fc)/alln*100:.0f}%)、占名義 {fc['名義額'].sum()/t['名義額'].sum()*100:.0f}%", flush=True)
pairs = sorted({(str(s).zfill(4), str(pd.Timestamp(d).date())) for d, s in zip(fc["日期"], fc["股票"])})
CS = "fill_probe/_closetime_cache.pkl"; key = hashlib.md5(("#".join(f"{c}_{d}" for c, d in pairs)).encode()).hexdigest()
if os.path.exists(CS):
    b = pickle.load(open(CS, "rb")); M = b["M"] if b.get("k") == key else None
else: M = None
if M is None:
    M = {}; byc = {}
    for c, d in pairs: byc.setdefault(c, set()).add(d)
    print(f"讀 1m: {len(byc)} 檔/{len(pairs)} 日 ...", flush=True)
    for c, dset in byc.items():
        p = ONEF.get(c)
        if not p: continue
        try: m = pd.read_parquet(p, columns=["time", "close", "volume"])
        except Exception: continue
        tt = pd.to_datetime(m["time"]); m = m.assign(_d=tt.dt.normalize(), _m=(tt.dt.hour*60+tt.dt.minute), _sh=m["volume"].values*1000.0).sort_values("time")
        grp = {dt: g for dt, g in m.groupby("_d")}; ud = sorted(grp); pos = {dt: i for i, dt in enumerate(ud)}
        for ds in dset:
            g = grp.get(pd.Timestamp(ds))
            if g is None: continue
            i = pos[pd.Timestamp(ds)]; no = np.nan
            if i + 1 < len(ud):
                ng = grp[ud[i+1]]; n9 = ng[ng["_m"].values == 541]
                if len(n9): no = float(n9["close"].values[0])   # 隔天開盤(用 close 近似 open)
            M[(c, ds)] = dict(m=g["_m"].values, c=g["close"].values, sh=g["_sh"].values, cl_close=float(g["close"].values[-1]), next_open=no)
    os.makedirs("fill_probe", exist_ok=True); pickle.dump({"k": key, "M": M}, open(CS, "wb"))
print(f"可用 (code,date) 分钟K: {len(M)}", flush=True)

def simulate(T):
    # T=開始分鐘(hour*60+min); 回傳(總name, 殘留過夜name, 實際pnl元, 理想pnl元)
    tot = resid = pnlA = pnlI = 0.0
    for _, r in fc.iterrows():
        code = str(r["股票"]).zfill(4); ds = str(pd.Timestamp(r["日期"]).date())
        pr = float(r["回測進場價"]); notional = float(r["名義額"]); side = r["方向"]
        mb = M.get((code, ds))
        if not mb:   # 無資料: 视为理想(不變)
            tot += notional; pnlI += notional*((pr-mb["cl_close"])/pr if mb else 0.0); continue
        m = mb["m"]; mask = (m >= T) & (m <= 805)
        if not mask.any():
            tot += notional; pnlI += notional*((pr-mb["cl_close"])/pr); continue
        cv = float((mb["c"][mask]*mb["sh"][mask]).sum()); shs = float(mb["sh"][mask].sum())
        vwap = cv/shs if shs > 0 else mb["cl_close"]
        f = min(1.0, CAP*cv/notional) if notional > 0 else 1.0
        no = mb["next_open"];
        if not np.isfinite(no): no = vwap   # 無隔天資料 -> 視為可全平
        exitpx = f*vwap + (1.0-f)*no
        pn = (pr-exitpx)/pr if side == "SHORT" else (exitpx-pr)/pr
        pnI = (pr-mb["cl_close"])/pr if side == "SHORT" else (mb["cl_close"]-pr)/pr
        tot += notional; resid += notional*(1.0-f); pnlA += notional*pn; pnlI += notional*pnI
    return tot, resid, pnlA, pnlI

years = (pd.to_datetime(fc["日期"]).max()-pd.to_datetime(fc["日期"]).min()).days/365.25
print("\n=== 平倉開始時間評估 (cap=10%%, 成交≈窗VWAP, 平不掉→隔天開盤) ===", flush=True)
print(f"{'開始 T':>10} | {'隔夜殘留(占name)':>18} | {'vs理想13:25 成本':>16} | {'對年均影響':>10} | {'保守现实年均*':>12}")
print("-"*82)
for T, lbl in [(805,"13:25一次"),(800,"13:20"),(795,"13:15"),(790,"13:10"),(780,"13:00"),(750,"12:30"),(720,"12:00")]:
    tot, resid, pnlA, pnlI = simulate(T)
    cost = (pnlI - pnlA)                      # 正=較理想13:25 少賺(成本)
    ann_imp = cost/4_500_000/years*100.0
    print(f"{lbl:>10} | {resid/tot*100:>17.1f}% | {-cost/1e4:>14.0f}萬 | {-ann_imp:>+9.1f}% | {'':>12}", flush=True)
print("\n* 保守现实年均 = +147.4%(進場cap) 再扣『平倉端相對理想13:25 的額外成本』; 13:25一次=先前 -19.5pp 的來源")
