import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]: os.environ[k]="1"
import sys, io, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

# ================= v21 冠軍配置 =================
TH=-0.012; QMIN=0.20; SS=5.5; GAPMAX=0.08; ZTMIN=0.014; LIQ=0.25; EXPO=1.0
BRAKE=((-0.03,0.30),(-0.06,0.12)); SLIP=1.0
COVER_MIN=20.0

# 1 分鐘 per-stock 資料：真實 09:01 成交價 + 入場後(09:02..13:25)走勢（因果回放）
ONE=r"D:\Codex\2026-11-14\new-chat-2\outputs\capital_stock_data\data\fugle_1m"
_ONE={f[:-8]:os.path.join(ONE,f) for f in os.listdir(ONE)} if os.path.isdir(ONE) else {}

def _paths(stk):
    """{date(Timestamp): (fill, hi, lo, cl)}: 09:01 開盤成交價 + 僅入場後(09:02..13:25) K 的高低收。
    只用入場後的 K，避免把 09:01 之前的價格當成前視。"""
    p = _ONE.get(str(stk))
    if not p:
        return {}
    try:
        m = pd.read_parquet(p, columns=["time", "open", "high", "low", "close"])
    except Exception:
        return {}
    t = pd.to_datetime(m["time"])
    mins = (t.dt.hour * 60 + t.dt.minute).values
    d = t.dt.normalize()
    out = {}
    for dt, g in m.assign(_m=mins).groupby(d):
        gm = g["_m"].values
        fb = g[gm == 541]                       # 09:01 成交價
        if len(fb) == 0:
            continue
        fill = float(fb["open"].iloc[0])
        af = g[(gm >= 542) & (gm <= 805)]       # 09:02..13:25
        if len(af) == 0 or not (np.isfinite(fill) and fill > 0):
            continue
        out[dt] = (fill, float(af["high"].max()), float(af["low"].min()), float(af["close"].iloc[-1]))
    return out

ap = argparse.ArgumentParser()
ap.add_argument("--start", default="2023-05-23")
ap.add_argument("--end", default="2026-12-31")
ap.add_argument("--no-replay", action="store_true", help="不讀 1m，只用引擎(已內含真實 09:01 成本)")
a = ap.parse_args(); S, E = a.start, a.end; tag = "%s_%s" % (S, E)

from v13_engine import exit_of_legal, CAP0, COST
from v13_executable import FC_COST, SL_COST
import v13_target as T
D = T.D.copy(); D["_d"] = pd.to_datetime(D["date"])
mon = D[(D["_d"] >= pd.Timestamp(S)) & (D["_d"] <= pd.Timestamp(E))]
if mon.empty:
    print("區間 %s~%s 無資料" % (S, E)); sys.exit(0)

# 引擎 entry_cost 已預設內含真實 09:01 滑價(S3_REAL_ENTRY)，故此 aggregate 為真實口徑
BASEF = mon[(~mon["blocked"].values) & (mon["pred_q"].fillna(-1) >= QMIN) & (mon["price_dir"] < TH)]
T.GROUPS = {d: g for d, g in BASEF.groupby("date")}; T.days = sorted(BASEF["date"].unique())
r = T.run(slip_scale=SLIP, date_min=S, s3=False, size_scale=SS, exposure=EXPO,
          gap_max=GAPMAX, zt_min_dist=ZTMIN, liq=LIQ, brake=BRAKE, capture=True)

ctx = {}
for _, rr in BASEF.iterrows():
    pr = float(rr["entry"])
    z = (float(rr["lu"]) - pr) / pr if rr["direction"] == "SHORT" else (pr - float(rr["ld"])) / pr
    ctx[(str(pd.Timestamp(rr["date"]).date()), str(rr["stock"]), rr["direction"])] = dict(
        rank=int(rr["_rank"]), gap=float(rr["adj_gap"]), pdir=float(rr["price_dir"]), zdist=z,
        predq=float(rr["pred_q"]), direction=rr["direction"], lu=float(rr["lu"]),
        ld=float(rr["ld"]), tk=float(rr["tick"]), tp=float(rr["tp"]))

def real_exit(c, fill, phi, plo, pcl):
    """真實 09:01 成交價 entry + 僅入場後 OHLC 回放，套用引擎相同法規出場規則。回傳(出場價, 淨pct, 原因)。"""
    ex, _, _, reason, gross = exit_of_legal(c["direction"], fill, phi, plo, pcl, c["lu"], c["ld"], c["tk"], c["tp"])
    if reason == "13:25 強制平倉":
        gross -= FC_COST
    elif reason.startswith("停損"):
        gross -= SL_COST
    gross -= 2 * COST
    return ex, gross, reason

td = []; daily = {}; cov_en = []; cov_re = []; cache = {}
for (dd, code, side, notional, gross, reason, pr, ex) in r["trades"]:
    c = ctx.get((dd, code, side), {})
    lots = int(round(notional / 1000.0 / pr)) if pr > 0 else 0
    row = dict(日期=dd, 股票=code, 方向=side, 模型排名=c.get("rank", ""),
        跳空pct=round(c.get("gap", np.nan) * 100, 2) if c else "",
        衰竭pct=round(c.get("pdir", np.nan) * 100, 2) if c else "",
        距限制pct=round(c.get("zdist", np.nan) * 100, 2) if c else "",
        pred_q=round(c.get("predq", np.nan), 3) if c else "",
        張數=lots, 名義額=round(notional),
        回測進場價=round(pr, 3), 回測出場價=round(ex, 3), 回測出場原因=reason,
        回測淨pct=round(gross * 100, 3), 回測淨額元=round(notional * gross))
    if not a.no_replay and c:
        if code not in cache:
            cache[code] = _paths(code)
        pt = cache[code].get(pd.Timestamp(dd))
        if pt is not None:
            f, phi, plo, pcl = pt
            rex, rgross, rreason = real_exit(c, float(f), phi, plo, pcl)
            row["真實進場價0901"] = round(float(f), 3); row["真實出場價"] = round(rex, 3)
            row["真實出場原因"] = rreason; row["真實淨pct"] = round(rgross * 100, 3)
            row["真實淨額元"] = round(notional * rgross)
            cov_en.append(gross); cov_re.append(rgross)
        else:
            for k in ["真實進場價0901", "真實出場價", "真實出場原因", "真實淨pct", "真實淨額元"]:
                row[k] = ""
    td.append(row)
    e = daily.setdefault(dd, [0.0, 0, 0]); e[0] += notional * gross; e[1] += 1; e[2] += 1 if gross > 0 else 0
tdf = pd.DataFrame(td).sort_values(["日期", "模型排名"])
pp = r"%s\v21_trades_%s.csv" % (os.getcwd(), tag); tdf.to_csv(pp, index=False, encoding="utf-8-sig")
print("WROTE", pp, len(tdf), "筆")

cov_by_day = {pd.Timestamp(d): (g["price_dir"].notna().mean() * 100 if len(g) else 0.0) for d, g in mon.groupby("date")}
rows = []; cum = 0.0
for d in sorted(cov_by_day):
    ds = pd.Timestamp(d).strftime("%Y-%m-%d"); cg = mon[mon["date"] == d]
    e = daily.get(ds, [0.0, 0, 0]); net = e[0]; nf = e[1]; w = e[2]; cum += net
    rows.append(dict(日期=ds, 候選數=int((~cg["blocked"].values).sum()), 一分鐘覆蓋pct=round(cov_by_day[d], 0),
        可評估=("Y" if cov_by_day[d] >= COVER_MIN else "N"), 成交筆=nf, 勝=w, 敗=nf - w, 淨額元=round(net),
        淨pct對450萬=round(net / CAP0 * 100, 3), 累計淨額元=round(cum),
        備註=("OK" if cov_by_day[d] >= COVER_MIN else "缺1m資料")))
ddf = pd.DataFrame(rows); pq = r"%s\v21_daily_%s.csv" % (os.getcwd(), tag); ddf.to_csv(pq, index=False, encoding="utf-8-sig")
print("WROTE", pq, len(ddf), "列")

yrs = sorted(r["yearly"]); rets = [r["yearly"][k] / CAP0 * 100 for k in yrs]
win = 100.0 * sum(1 for t in r["trades"] if t[3] * t[4] > 0) / max(len(r["trades"]), 1)
dpath = pd.DataFrame(r["daily"], columns=["date", "yuan", "book", "dd"]); dpath["year"] = pd.to_datetime(dpath["date"]).dt.year
yrows = []
for y in yrs:
    sub = dpath[dpath["year"] == y]
    yrows.append(dict(年=y, 報酬pct=round(rets[yrs.index(y)], 1), 年內最大回撤pct=round(sub["dd"].min() * 100, 2),
                      成交=sum(1 for k in daily if k.startswith(str(y)) and daily[k][1] > 0),
                      獲利日=sum(1 for k in daily if k.startswith(str(y)) and daily[k][0] > 0)))
ydf = pd.DataFrame(yrows); py = r"%s\v21_yearly_%s.csv" % (os.getcwd(), tag); ydf.to_csv(py, index=False, encoding="utf-8-sig")
print("WROTE", py)

print("\n=== 全期驗證（引擎=真實 09:01 成本口徑, entry_cost 已內含 S3_REAL_ENTRY）===")
print("區間 %s~%s | 交易筆=%d 淨勝率 %.1f%%" % (S, E, len(r["trades"]), win))
print("年均(平均) %+.1f%% | 部位MDD %+.2f%% | 筆/日 %.1f" % (np.mean(rets), r["mdd"], r["per_day"]))
print("引擎 S3_REAL_ENTRY=%s S3_REAL_SHORT_ENTRY=%s" % (T.S3_REAL_ENTRY, T.S3_REAL_SHORT_ENTRY))
if len(cov_en):
    be = np.mean(cov_en) * 100; br = np.mean(cov_re) * 100
    print("\n=== 1m 逐筆因果回放校準（僅有 1m 覆蓋的 %d 筆, 只取入場後 K）===" % len(cov_en))
    print("引擎每筆淨pct 平均 %+.3f%% | 真實09:01每筆淨pct 平均 %+.3f%% | 差 %+.3f%%/筆" % (be, br, br - be))
    print("引擎勝率 %.1f%% | 真實回放勝率 %.1f%%" % ((np.array(cov_en) > 0).mean() * 100, (np.array(cov_re) > 0).mean() * 100))
print("\n逐年:")
for y in yrows:
    print("  %s: 報酬 %+6.1f%%  年內回撤 %+5.2f%%  成交日 %d 獲利日 %d" % (y["年"], y["報酬pct"], y["年內最大回撤pct"], y["成交"], y["獲利日"]))
