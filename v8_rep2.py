import pandas as pd, numpy as np, pickle, warnings; warnings.filterwarnings("ignore")
CAP0=4_500_000
L=[]
def P(s=""): L.append(s)

def stats(eq, tr, lab):
    e=pd.Series(eq); dts=pd.DatetimeIndex([pd.Timestamp(x[0]) for x in tr])
    yrs=(dts[-1]-dts[0]).days/365.25
    cg=(e.iloc[-1]/CAP0)**(1/yrs)-1
    dd=((e-e.cummax())/e.cummax())
    mdd=dd.min(); mdd_i=int(dd.values.argmin())
    rr=e.pct_change().fillna(0)
    sharpe=rr.mean()/rr.std()*np.sqrt(243)
    n=sum(x[1] for x in tr)
    P("="*100); P("  GAP FADE v8  |  完整績效報告（整張・450萬・零融資・成本 0.109%/邊）")
    P("="*100)
    P(f"  CAGR               {cg*100:8.1f}%")
    P(f"  MDD                {mdd*100:8.2f}%   (peak {dts[int(np.argmax(e.values[:mdd_i+1]))].date()} -> trough {dts[mdd_i].date()})")
    P(f"  Sharpe             {sharpe:8.2f}")
    P(f"  Calmar             {abs(cg/mdd):8.1f}")
    P(f"  Final equity  {e.iloc[-1]/10000:>14,.0f} 萬   ({e.iloc[-1]/CAP0:,.0f}x)")
    P(f"  Period          {dts[0].date()} ~ {dts[-1].date()}  ({yrs:.1f} years)")
    act=sum(1 for x in tr if x[1]>0)
    P(f"  Trading days      {act:,} / {len(tr):,}   ({act/len(tr)*100:.0f}%)")
    P(f"  Trades            {n:,}   avg {n/act:.1f}/active day")
    day=[x[2] for x in tr]
    P(f"  Positive days     {np.mean([d>0 for d in day])*100:.1f}%")
    P(f"  Avg day return    {np.mean(day)*100:+.3f}%")
    expo=[x[3] for x in tr]
    P(f"  Avg exposure      {np.mean([x for x in expo])*100:.1f}%   max {max(expo)*100:.0f}%")
    allpos=np.concatenate([x[6] for x in tr if x[1]>0]) if n else np.array([0])
    P(f"  Avg position      {np.mean(allpos)*100:.2f}% of equity   max {allpos.max()*100:.1f}%")
    pn=np.concatenate([x[5] for x in tr if x[1]>0])
    P(f"  Per-trade PnL     avg {pn.mean()*100:+.3f}%   win {(pn>0).mean()*100:.1f}%")
    w=pn[pn>0]; lo=pn[pn<=0]
    P(f"  Avg win/loss      {w.mean()*100:+.2f}% / {lo.mean()*100:+.2f}%   盈虧比 {abs(w.mean()/lo.mean()):.2f}")
    P(f"  Profit factor     {w.sum()/abs(lo.sum()):.2f}")
    P(f"  Max single win    {pn.max()*100:+.2f}%   Max single loss {pn.min()*100:+.2f}%")
    zt=np.concatenate([x[7] for x in tr if x[1]>0])
    P(f"  觸板(漲/跌停)停損占比 {zt.mean()*100:.1f}%")
    P("")
    # yearly
    P("="*100); P("  逐年績效"); P("="*100)
    P(f"{'年':<7}{'報酬%':>10}{'年內MDD%':>10}{'交易筆':>9}{'勝率%':>8}{'均PnL%':>9}{'均筆/日':>9}{'觸板停損%':>10}")
    P("-"*74)
    yr={}
    for x in tr:
        y=x[8]; yr.setdefault(y,{"d":[],"n":0,"pn":[],"zt":[],"nd":0,"ex":[]})
        yr[y]["d"].append(x[2]); yr[y]["n"]+=x[1]
        if x[1]>0:
            yr[y]["pn"]+=list(x[5]); yr[y]["zt"]+=list(x[7]); yr[y]["nd"]+=1; yr[y]["ex"].append(x[3])
    for y in sorted(yr):
        v=yr[y]; e2=pd.Series(v["d"]); eq2=e2.cumsum()
        cum=np.prod([1+d for d in v["d"]])-1
        run=np.maximum.accumulate(np.cumsum(np.log(np.array(v["d"])+1)))
        m2=(np.cumsum(np.log(np.array(v["d"])+1))-run).min()
        pn2=np.array(v["pn"]); zt2=np.array(v["zt"])
        P(f"{y:<7}{cum*100:>10.1f}{m2*100:>10.1f}{v['n']:>9,}{(pn2>0).mean()*100:>8.1f}{pn2.mean()*100:>9.2f}{v['n']/max(v['nd'],1):>9.1f}{zt2.mean()*100:>10.1f}")
        yr[y]["ret"]=cum
    P("")
    # monthly
    P("="*100); P("  逐月績效（%）"); P("="*100)
    mon={}
    for x in tr:
        d=pd.Timestamp(x[0]); mon[(d.year,d.month)]=mon.get((d.year,d.month),1.0)*(1+x[2])
    years=sorted(set(k[0] for k in mon))
    P("  "+f"{'年':<6}"+"".join(f"{m:>7}" for m in range(1,13))+"   全年")
    neg=0; tot=0; vals=[]
    for y in years:
        row=[]; ann=1.0
        for m in range(1,13):
            k=(y,m)
            if k in mon:
                v=mon[k]-1; row.append(f"{v*100:7.1f}"); ann*=mon[k]; vals.append(v); tot+=1
                if v<0: neg+=1
            else: row.append("      -")
        P("  "+f"{y:<6}"+"".join(row)+f"  {ann*100-100:>7.1f}")
    P(f"\n  月度統計: 正報酬 {tot-neg}/{tot} ({(tot-neg)/tot*100:.1f}%)   最差月 {min(vals)*100:.2f}%   月均 {np.mean(vals)*100:+.2f}%")
    P("")
    # rolling
    P("="*100); P("  滾動期間穩定性"); P("="*100)
    de=e.diff().fillna(0)
    for k,lab in [(63,"3個月"),(126,"6個月"),(252,"12個月"),(504,"24個月"),(992,"48個月")]:
        if len(e)<=k: continue
        r=e.shift(-k)/e; r=r.dropna()
        P(f"  {lab:<7} 樣本 {len(r):>6,}   正報酬 {(r>1).mean()*100:5.1f}%   最差 {((r-1).min())*100:8.2f}%   中位 {((r-1).median())*100:+8.2f}%")
    P(f"\n  日損益分佈: 最差 {min(day)*100:.2f}%   P1 {np.percentile(day,1)*100:.2f}%   中位 {np.median(day)*100:+.3f}%   P99 {np.percentile(day,99)*100:+.2f}%")
    P("")
    # sub-period CAGR
    P("="*100); P("  區間 CAGR（真實起訖）"); P("="*100)
    def seg(a,b,lab):
        s=e.loc[a:b]
        if len(s)<50: return
        yy=(s.index[-1]-s.index[0]).days/365.25
        cg2=(s.iloc[-1]/s.iloc[0])**(1/yy)-1
        dd2=((s-s.cummax())/s.cummax()).min()
        r2=s.pct_change().fillna(0)
        P(f"{a[:7]} ~ {b[:7]}   {yy:5.2f}y   CAGR {cg2*100:7.1f}%   MDD {dd2*100:6.2f}%   Sharpe {r2.mean()/r2.std()*np.sqrt(243):5.2f}")
    es=pd.Series(eq[1:],index=dts)
    e=es
    for a,b,lab in [("2010-01","2019-12",""),("2015-01","2019-12",""),("2016-01","2019-12",""),
                    ("2020-01","2022-12",""),("2021-01","2023-12",""),("2022-01","2024-12",""),
                    ("2023-01","2025-12",""),("2024-01","2025-12",""),("2025-01","2026-06","")]:
        seg(a+"-01",b+"-28",lab)
    P("")
    P("  滾動窗口 CAGR（所有歷史起點）")
    for k,lab in [(252,"1年"),(504,"2年"),(756,"3年")]:
        r=(e.shift(-k)/e).dropna()
        cg3=(r)**(365.25/((k)/243*365.25))-1
        P(f"  {lab:<4} n={len(r):,}   正 {(cg3>0).mean()*100:5.1f}%   最差 {cg3.min()*100:8.1f}%   P5 {np.percentile(cg3,5)*100:7.1f}%   中位 {cg3.median()*100:+8.1f}%")
    return yr

eqL=pickle.load(open("v8_eq_curves.pkl","rb"))
for lab in ["整張"]:
    eq,tr=eqL[lab], pickle.load(open("v8_lot_1.pkl","rb"))["tr"]
    stats(eq,tr,lab)
open("v8_final_report.txt","w",encoding="utf-8").write("\n".join(L))
print("\n".join(L))
