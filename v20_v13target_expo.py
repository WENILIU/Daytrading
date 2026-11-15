import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

DMIN = "2023-05-23"
MASK23 = (pd.to_datetime(T.D["date"]) >= pd.Timestamp(DMIN)) & (~T.D["blocked"].values)
def run_cfg(qmin=None, **kw):
    Dw = T.D[MASK23]
    if kw.pop("s3", True): Dw = Dw[Dw["s3_pass"]]
    if qmin is not None: Dw = Dw[Dw["pred_q"] >= qmin]
    T.GROUPS = {d: g for d, g in Dw.groupby("date")}
    T.days = sorted(Dw["date"].unique())
    r = T.run(slip_scale=1.0, date_min=DMIN, s3=False, **kw)
    yrs = sorted(r["yearly"]); rets = [r["yearly"][k]/T.CAP0*100 for k in yrs]
    return r, yrs, rets

print("=== exposure 掃描（size=1.0, s3=True, 2023-05+ 全成本）===")
print("%-8s %8s %9s %7s %8s %8s %s" % ("exposure","年均%","部位MDD%","calmar","筆/日","曝險max","逐年%"))
for ex in [1.0,1.2,1.5,1.75,2.0,2.5,3.0]:
    r, yrs, rets = run_cfg(size_scale=1.0, exposure=ex)
    ok = " <== 達標" if (np.mean(rets) >= 200 and r["mdd"] >= -5.0) else ""
    print("%-8.2f %8.1f %9.2f %7.1f %8.1f %8.1f  %s%s" %
          (ex, np.mean(rets), r["mdd"], abs(np.mean(rets)/r["mdd"]), r["per_day"], r["expo_max"],
           " ".join("%d %+.0f"%(y,v) for y,v in zip(yrs,rets)), ok))

print()
print("=== 建議配置逐年 + 每年部位回撤（exposure=1.5 與 2.0）===")
for ex in [1.5, 2.0]:
    r, yrs, rets = run_cfg(size_scale=1.0, exposure=ex)
    print("  exposure=%.1f: 年均%+.1f%% 部位MDD %+.2f%% 筆/日 %.1f 曝險max %.0f%%" %
          (ex, np.mean(rets), r["mdd"], r["per_day"], r["expo_max"]))
    # monthly worst-drawdown by year from daily path
    daily = pd.DataFrame(r["daily"], columns=["date","yuan","book","dd"])
    daily["year"] = pd.to_datetime(daily["date"]).dt.year
    for y in yrs:
        sub = daily[daily["year"] == y]
        print("      %d: 報酬 %+.0f%%  年內最差回撤 %+.2f%%" % (y, rets[yrs.index(y)], sub["dd"].min()*100))
