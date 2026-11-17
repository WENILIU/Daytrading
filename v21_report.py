import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]: os.environ[k]="1"
import sys, io, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

# ================= v21 冠軍配置 =================
TH=-0.012; QMIN=0.20; SS=5.5; GAPMAX=0.08; ZTMIN=0.014; LIQ=0.25; EXPO=1.0
BRAKE=((-0.03,0.30),(-0.06,0.12)); SLIP=1.0
COVER_MIN=20.0   # 每日 >=20% 候選有 1m 價才算「可評估」，僅作標記，不影響引擎成交

ap=argparse.ArgumentParser()
ap.add_argument("--start",default="2023-05-23")
ap.add_argument("--end",default="2026-12-31")
a=ap.parse_args(); S,E=a.start,a.end; tag="%s_%s"%(S,E)

import v13_target as T
D=T.D.copy(); D["_d"]=pd.to_datetime(D["date"])
mon=D[(D["_d"]>=pd.Timestamp(S)) & (D["_d"]<=pd.Timestamp(E))]
if mon.empty: print("區間 %s~%s 無資料"%(S,E)); sys.exit(0)

# 忠於回測：引擎跑全部通過預過濾的候選（不限覆蓋率門檻）
BASEF=mon[(~mon["blocked"].values) & (mon["pred_q"].fillna(-1)>=QMIN) & (mon["price_dir"]<TH)]
T.GROUPS={d:g for d,g in BASEF.groupby("date")}; T.days=sorted(BASEF["date"].unique())
r=T.run(slip_scale=SLIP, date_min=S, s3=False, size_scale=SS, exposure=EXPO,
        gap_max=GAPMAX, zt_min_dist=ZTMIN, liq=LIQ, brake=BRAKE, capture=True)

# 交易明細 + join 上下文
ctx={}
for _,rr in BASEF.iterrows():
    pr=float(rr["entry"])
    z=(float(rr["lu"])-pr)/pr if rr["direction"]=="SHORT" else (pr-float(rr["ld"]))/pr
    ctx[(str(pd.Timestamp(rr["date"]).date()),str(rr["stock"]),rr["direction"])]=dict(
        rank=int(rr["_rank"]),gap=float(rr["adj_gap"]),pdir=float(rr["price_dir"]),zdist=z,predq=float(rr["pred_q"]))
td=[]; daily={}
for (dd,code,side,notional,gross,reason,pr,ex) in r["trades"]:
    c=ctx.get((dd,code,side),{})
    td.append(dict(日期=dd,股票=code,方向=side,模型排名=c.get("rank",""),
        跳空pct=round(c.get("gap",np.nan)*100,2) if c else "", 衰竭pct=round(c.get("pdir",np.nan)*100,2) if c else "",
        距限制pct=round(c.get("zdist",np.nan)*100,2) if c else "", pred_q=round(c.get("predq",np.nan),3) if c else "",
        張數=int(round(notional/1000.0/pr)) if pr>0 else 0, 名義額=round(notional),
        進場價=round(pr,3), 出場價=round(ex,3), 出場原因=reason, 淨pct=round(gross*100,3), 淨額元=round(notional*gross)))
    e=daily.setdefault(dd,[0.0,0,0]); e[0]+=notional*gross; e[1]+=1; e[2]+=1 if gross>0 else 0
tdf=pd.DataFrame(td).sort_values(["日期","模型排名"])
pp=r"%s\v21_trades_%s.csv"%(os.getcwd(),tag); tdf.to_csv(pp,index=False,encoding="utf-8-sig")
print("WROTE",pp,len(tdf),"筆")

# 逐日摘要（含覆蓋標記）
cov_by_day={pd.Timestamp(d):(g["price_dir"].notna().mean()*100 if len(g) else 0.0) for d,g in mon.groupby("date")}
rows=[]; cum=0.0
for d in sorted(cov_by_day):
    ds=pd.Timestamp(d).strftime("%Y-%m-%d"); cg=mon[mon["date"]==d]
    e=daily.get(ds,[0.0,0,0]); net=e[0]; nf=e[1]; w=e[2]; cum+=net
    rows.append(dict(日期=ds,候選數=int((~cg["blocked"].values).sum()),一分鐘覆蓋pct=round(cov_by_day[d],0),
        可評估=("Y" if cov_by_day[d]>=COVER_MIN else "N"),成交筆=nf,勝=w,敗=nf-w,淨額元=round(net),
        淨pct對450萬=round(net/T.CAP0*100,3),累計淨額元=round(cum),
        備註=("OK" if cov_by_day[d]>=COVER_MIN else "⚠️缺1m資料")))
ddf=pd.DataFrame(rows); pq=r"%s\v21_daily_%s.csv"%(os.getcwd(),tag); ddf.to_csv(pq,index=False,encoding="utf-8-sig")
print("WROTE",pq,len(ddf),"列")

# ============ 全期 / 逐年 驗證（與回測標稱同口径）============
yrs=sorted(r["yearly"]); rets=[r["yearly"][k]/T.CAP0*100 for k in yrs]
win=100.0*sum(1 for t in r["trades"] if t[3]*t[4]>0)/max(len(r["trades"]),1)
# 逐年最大回撤（部位）
dpath=pd.DataFrame(r["daily"],columns=["date","yuan","book","dd"]); dpath["year"]=pd.to_datetime(dpath["date"]).dt.year
yrows=[]
for y in yrs:
    sub=dpath[dpath["year"]==y]
    nd=len(daily_dates:=[k for k in daily if k.startswith(str(y))])
    yrows.append(dict(年=y, 報酬pct=round(rets[yrs.index(y)],1), 年內最大回撤pct=round(sub["dd"].min()*100,2),
                      成交=sum(1 for k in daily if k.startswith(str(y)) and daily[k][1]>0),
                      獲利日=sum(1 for k in daily if k.startswith(str(y)) and daily[k][0]>0)))
ydf=pd.DataFrame(yrows); py=r"%s\v21_yearly_%s.csv"%(os.getcwd(),tag); ydf.to_csv(py,index=False,encoding="utf-8-sig")
print("WROTE",py)
print("\n=== 全期驗證（同回測口徑）===")
print("區間 %s~%s | 實際交易筆=%d 覆蓋日=%d | 淨勝率 %.1f%%"%(
    S,E,len(r["trades"]),len([k for k in daily if daily[k][1]>0]),win))
print("年均(平均) %+.1f%% | 部位MDD %+.2f%% | 筆/日 %.1f"%(np.mean(rets), r["mdd"], r["per_day"]))
print("回測標稱(決策檔): 年均+270.6%% MDD-4.29%% 勝率78.4%% 筆/日3.8")
print("\n逐年:")
for y in yrows: print("  %s: 報酬 %+6.1f%%  年內回撤 %+5.2f%%  成交日 %d 獲利日 %d"%(
    y["年"],y["報酬pct"],y["年內最大回撤pct"],y["成交"],y["獲利日"]))
