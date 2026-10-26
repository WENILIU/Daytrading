import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
exec(open("v13_dstune.py",encoding="utf-8").read().split("d=pd.read_pickle")[0])
d=pd.read_pickle("signals_v13.pkl"); d=d[d["pred"].notna()].copy(); d["stock"]=d["stock"].astype(str)
d["touch_zt"]=np.where(d["direction"]=="SHORT",d["day_high"]>=d["lu"]-1e-9,d["day_low"]<=d["ld"]+1e-9)
rec=run(d,bpmul=1.0,dsfac=1.0)
e=pd.Series([1+x[1] for x in rec],index=[x[0] for x in rec]).cumprod()
v8=pickle.load(open("final_trades_realdisp.pkl","rb"))["v8_real"]
e8=pd.Series([1+x[1] for x in v8],index=[x[0] for x in v8]).cumprod()
def yearly(e):
    m=e.resample("YE").last()/e.resample("YE").first()-1
    dd=e.groupby(e.index.year).apply(lambda s:((s-s.cummax())/s.cummax()).min())
    return (m*100).round(1), dd
y13,dd13=yearly(e); y8,dd8=yearly(e8)
d13=pd.DataFrame([(x[0],x[1],x[2],x[3]) for x in rec],columns=["date","pnl","n","expo"])
d8=pd.DataFrame([(x[0],x[1],x[2],x[3]) for x in v8],columns=["date","pnl","n","expo"])
t=pd.DataFrame({"v8_ret%":y8,"v8_mdd%":(dd8*100).round(1),"v8_n":d8.groupby(d8["date"].dt.year)["n"].sum(),
                "v13_ret%":y13,"v13_mdd%":(dd13*100).round(1),"v13_n":d13.groupby(d13["date"].dt.year)["n"].sum()}).dropna(subset=["v8_ret%"])
t["ratio"]=t["v13_ret%"]/t["v8_ret%"]
print("=== v8 vs v13 (bpm=1.0, ds removed) 逐年 ===")
print(t.to_string(float_format=lambda v:f"{v:9.1f}"))
def perf2(e,lab):
    rr=e.pct_change().fillna(0); yrs=(e.index[-1]-e.index[0]).days/365.25
    cg=(e.iloc[-1]/e.iloc[0])**(1/yrs)-1; dd=((e-e.cummax())/e.cummax()).min()
    def seg(a,b):
        s=e.loc[a:b]; yy=(s.index[-1]-s.index[0]).days/365.25
        return ((s.iloc[-1]/s.iloc[0])**(1/yy)-1)*100
    print(f"{lab:<26} CAGR {cg*100:7.1f}%  MDD {dd*100:6.2f}%  Sharpe {rr.mean()/rr.std()*np.sqrt(243):5.2f}  Calm {abs(cg/dd):5.1f}  2015-19 {seg('2015-01-01','2019-12-31'):7.1f}%  2023-25 {seg('2023-01-01','2025-12-31'):7.1f}%  比值 {seg('2023-01-01','2025-12-31')/seg('2015-01-01','2019-12-31'):5.2f}")
print("")
perf2(e8,"v8 (real disposal)")
perf2(e,"v13 bpm=1.0 ds removed")
print("")
mm=(e.resample("ME").last()/e.resample("ME").first()-1)*100
piv=pd.DataFrame({"y":mm.index.year,"m":mm.index.month,"v":mm.values}).pivot_table(index="y",columns="m",values="v")
print("=== v13 逐月% (2023-) ===")
print(piv.loc[2023:].round(1).to_string())
print(f"\n正報酬月 {int((mm>0).sum())}/{len(mm)}  最差月 {mm.min():.2f}%  月均 {mm.mean():.2f}%")
t.to_csv("v8_vs_v13.csv",encoding="utf-8-sig")
