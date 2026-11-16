import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]:
    os.environ[k]="1"
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T
# ============================================================
# v21 最佳配置（沿用 450 万、獲利出金、不借錢 exposure=1.0）
# 在 S3 -0.8%/size=1.4 (+199.1%/-4.29%/勝率72.2%) 基礎上，
# 加入三個「品質/風險」過濾器把勝率與報酬拉高、把尾部壓低，
# 再用 size 把 MDD budget 重新兑现。
#   s3 收緊到 -1.2%  : 只留較強的量價竭盡，勝率 72->75、MDD 4.29->3.32
#   gap_max=0.08     : 避開 |gap|>=8% 的進場成本尾端
#   zt_min_dist=0.014: 進場價距漲跌幅限制 <1.4% 的不做（避開 -3.1% pin 尾部）
#   size_scale=5.5   : 在 MDD budget 內重新放大部位
# ============================================================
DMIN="2023-05-23"
CFG=dict(th=-0.012, qmin=0.20, ss=5.5, gap_max=0.08, zt_min_dist=0.014)
BASE = T.D[(pd.to_datetime(T.D["date"])>=pd.Timestamp(DMIN)) & (~T.D["blocked"].values)]
Dw = BASE[(BASE["pred_q"]>=CFG["qmin"]) & (BASE["price_dir"]<CFG["th"])]
T.GROUPS={d:g for d,g in Dw.groupby("date")}; T.days=sorted(Dw["date"].unique())
r=T.run(slip_scale=1.0, date_min=DMIN, s3=False, size_scale=CFG["ss"], exposure=1.0,
        gap_max=CFG["gap_max"], zt_min_dist=CFG["zt_min_dist"], capture=True)
yrs=sorted(r["yearly"]); rets=[r["yearly"][k]/T.CAP0*100 for k in yrs]
win=100.0*sum(1 for t in r["trades"] if t[3]*t[4]>0)/len(r["trades"])
print("=== v21 最佳（釘 450 万、獲利出金、不借錢、slip 1.00 全成本、2023-05+）===")
print("配置: s3 th=%.1f%%  gap_max=%.0f%%  zt_min_dist=%.1f%%  size=%.1f" %
      (CFG["th"]*100, CFG["gap_max"]*100, CFG["zt_min_dist"]*100, CFG["ss"]))
print("  年均 %+.1f%%   部位MDD %+.2f%%   淨勝率 %.1f%%   筆/日 %.1f   曝險max %.0f%%   總筆數 %d" %
      (np.mean(rets), r["mdd"], win, r["per_day"], r["expo_max"], len(r["trades"])))
daily=pd.DataFrame(r["daily"],columns=["date","yuan","book","dd"]); daily["year"]=pd.to_datetime(daily["date"]).dt.year
for y in yrs:
    sub=daily[daily["year"]==y]
    print("    %d: 報酬 %+6.1f%%   年內最差部位回撤 %+5.2f%%" % (y, rets[yrs.index(y)], sub["dd"].min()*100))
print("\n對照基線 S3 -0.8% size1.4: 年均 +199.1%%  MDD -4.29%%  勝率 72.2%%")
