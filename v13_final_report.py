import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
exec(open("v13_dstune.py",encoding="utf-8").read().split("d=pd.read_pickle")[0])
d=pd.read_pickle("signals_v13.pkl"); d=d[d["pred"].notna()].copy(); d["stock"]=d["stock"].astype(str)
d["touch_zt"]=np.where(d["direction"]=="SHORT",d["day_high"]>=d["lu"]-1e-9,d["day_low"]<=d["ld"]+1e-9)
rec=run(d,bpmul=1.0,dsfac=1.0)
e=pd.Series([1+x[1] for x in rec],index=pd.to_datetime([x[0] for x in rec])).cumprod()
v8=pickle.load(open("final_trades_realdisp.pkl","rb"))["v8_real"]
e8=pd.Series([1+x[1] for x in v8],index=pd.to_datetime([x[0] for x in v8])).cumprod()
def build(e,rec):
    df=pd.DataFrame([(pd.to_datetime(x[0]),x[1],x[2],x[3]) for x in rec],columns=["date","pnl","n","expo"])
    yr=df.groupby(df["date"].dt.year)
    ret=(e.resample("YE").last()/e.resample("YE").first()-1)*100
    ret.index=ret.index.year
    mdd=df.groupby("date")["pnl"].sum().groupby(df["date"].dt.year).apply(lambda s:(( (1+s).cumprod()/(1+s).cumprod().cummax())-1).min())*100
    pn=np.concatenate([x[4] for x in rec])
    if any(len(x)>5 for x in rec):
        zt=np.concatenate([np.asarray(x[5],dtype=float) if len(x)>5 else np.full(len(x[4]),np.nan) for x in rec])
    else:
        zt=np.full(len(pn),np.nan)
    td=pd.DataFrame({"y":pd.to_datetime([pd.to_datetime(x[0]) for x in rec for _ in x[4]]).year,"p":pn,"z":zt})
    g=td.groupby("y")
    return pd.DataFrame({"ret%":ret,"mdd%":mdd,"n":yr["n"].sum(),"win%":g["p"].apply(lambda s:(s>0).mean()*100),
                         "avgPnL%":g["p"].mean(),"touch%":g["z"].mean()*100,"n/day":yr["n"].mean(),"expo%":yr["expo"].mean()*100})
T13=build(e,rec); T8=build(e8,v8)
J=T8.join(T13,lsuffix="_v8",rsuffix="_v13",how="inner")
L=[]
w=lambda s: L.append(s)
w("="*112); w("  GAP FADE v13  |  最終版完整績效（整張・450萬・零融資・成本 0.109%/邊・真實處置排除・無前視）")
w("="*112)
p=perf(rec); w(f"  CAGR {p['cagr']:.1f}%   MDD {p['mdd']:.2f}%   Sharpe {p['sharpe']:.2f}   Calmar {p['calm']:.1f}")
w(f"  交易 {sum(x[2] for x in rec):,} 筆  筆/日 {p['nperday']:.1f}  曝險 avg {p['expo']:.1f}% max {p['maxexpo']:.0f}%  觸板停損 {np.mean(np.concatenate([x[5] for x in rec]))*100:.1f}%")
w(f"  勝率 {np.mean(np.concatenate([x[4] for x in rec])>0)*100:.1f}%  均PnL {np.mean(np.concatenate([x[4] for x in rec]))*100:.3f}%")
w("")
w("="*112); w("  v8 vs v13 逐年（v13 自 2014 起，因子需 250/500 日歷史 + walk-forward 暖機）"); w("="*112)
w(f"{'年':>6} {'v8報酬%':>9} {'v13報酬%':>10} {'倍':>6} {'v8筆':>7} {'v13筆':>7} {'v13勝率%':>9} {'v13均PnL%':>10} {'v13觸板%':>9} {'v13曝險%':>9}")
for y,r in J.iterrows():
    ra = r["ret%_v13"]/r["ret%_v8"] if r["ret%_v8"]>0 else np.nan
    w(f"{int(y):>6} {r[chr(34)+chr(34)] if False else r['ret%_v8']:>9.1f} {r['ret%_v13']:>10.1f} {ra:>6.1f} {int(r['n_v8']):>7} {int(r['n_v13']):>7} {r['win%_v13']:>9.1f} {r['avgPnL%_v13']*100:>10.2f} {r['touch%_v13']:>9.1f} {r['expo%_v13']:>9.1f}")
w("")
w("  衰退曲線對照（真實日期區間 CAGR，非兩段平均）")
def segc(eq,a,b):
    ss=eq.loc[a:b]; yy=(ss.index[-1]-ss.index[0]).days/365.25
    return ((ss.iloc[-1]/ss.iloc[0])**(1/yy)-1)*100
PAIRS=[("2010-01-01","2011-12-31","2010-11","2025-01-01","2026-10-23","2025-26"),
       ("2015-01-01","2019-12-31","2015-19","2023-01-01","2025-12-31","2023-25")]
for lab,eq in [("v8 ",e8),("v13",e)]:
    for a1,a2,na,b1,b2,nb in PAIRS:
        try:
            ea=segc(eq,a1,a2); eb=segc(eq,b1,b2)
            w(f"    {lab}: {na} CAGR {ea:7.1f}%  ->  {nb} CAGR {eb:7.1f}%   比值 {eb/ea*100:5.0f}%  {'(衰退)' if eb<ea else '(轉正,已改善)'}")
        except Exception as ex: w(f"    {lab}: {na}->{nb} n/a ({ex})")
w("")
mm=(e.resample("ME").last()/e.resample("ME").first()-1)*100
piv=pd.DataFrame({"y":mm.index.year,"m":mm.index.month,"v":mm.values}).pivot_table(index="y",columns="m",values="v")
w("="*112); w("  v13 逐月績效（%）"); w("="*112)
w(piv.round(1).to_string())
w(f"\n  正報酬月 {int((mm>0).sum())}/{len(mm)} ({(mm>0).mean()*100:.1f}%)  最差月 {mm.min():.2f}%  月均 {mm.mean():.2f}%")
r3=e.pct_change().fillna(0)
for k,lab in [(63,"3個月"),(126,"6個月"),(252,"12個月")]:
    sr=((1+r3).rolling(k).apply(np.prod)-1).dropna()
    w(f"  Rolling {lab}: n={len(sr):,}  正 {(sr>0).mean()*100:5.1f}%  最差 {sr.min()*100:7.2f}%  中位 {sr.median()*100:8.2f}%")
txt="\n".join(L)
open("v13_final_report.txt","w",encoding="utf-8").write(txt)
print(txt)
