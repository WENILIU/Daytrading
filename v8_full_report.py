import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
exec(open("fast_nm.py").read().split("print(\"=\"*60)")[0])
df=pd.read_pickle("signals_pred_br.pkl"); df.index=pd.read_pickle("signals_pred.pkl").index
df["p"]=np.where(df["score"].values>=3,calc_pnl_vec(df,0.20,0.04),calc_pnl_vec(df,0.12,0.04))-2*COST
is_s=df["direction"]=="SHORT"
df["touch_zt"]=np.where(is_s,df["day_high"]>=df["lu"]-1e-9,df["day_low"]<=df["ld"]+1e-9)
df["year"]=pd.to_datetime(df["date"]).dt.year
BP1,BP2,M1,M2,MP=0.015,0.045,10.0,2.5,0.25
trail={}
for direc in ["SHORT","LONG"]:
    s=df[df["direction"]==direc].sort_values("date")
    s["t30"]=s["p"].rolling(30,min_periods=30).mean().shift(1)
    for dt,x in zip(s["date"],s["t30"].values): trail[(dt,direc)]=x
DD={}
for d in dates:
    if d not in g: continue
    sub=g[d]; ix=sub.index.values
    DD[d]={"bp":df.loc[ix,"base_pos"].values,"zt_d":df.loc[ix,"zt_dist"].values,
      "dirs":df.loc[ix,"direction"].values,"pnls":df.loc[ix,"p"].values,
      "pr":np.asarray(df.loc[ix,"pred_br"].values,dtype=float),
      "idx":ix,"zt":df.loc[ix,"touch_zt"].values,"yr":df.loc[ix,"year"].values,
      "t30":np.array([trail.get((d,x),np.nan) for x in df.loc[ix,"direction"]],dtype=float)}
def run():
    capital=CAPITAL; equity=[CAPITAL]; trades=[]
    for d in dates:
        if d not in DD: equity.append(capital); continue
        dd=DD[d]; peak=max(equity); cdd=(capital-peak)/peak
        rs=0.12 if cdd<-0.012 else (0.3 if cdd<-0.006 else 1.0)
        zm=np.where(dd["zt_d"]<BP1,M1,np.where(dd["zt_d"]<BP2,M2,1.0))
        p=dd["pr"]; kM=np.where(np.isfinite(p),np.clip(0.5+np.nan_to_num(p)/0.02,0,2),1.0)
        t=dd["t30"]; kT=np.where(np.isnan(t),1.0,np.clip(0.5+t/0.02,0.3,2.0))
        pos=dd["bp"]*zm*dir_scales[d]*rs*kM*kT
        pos=np.minimum(pos,MP); pos=np.minimum(pos,1.0)
        o=np.argsort(-np.nan_to_num(p,nan=-99))
        pos=pos[o]; pn=dd["pnls"][o]; dr_=dd["dirs"][o]; zt=dd["zt"][o]
        cum=np.cumsum(pos); mask=cum<=1.0
        if (~mask).any():
            fo=np.argmax(~mask); rem=1.0-(cum[fo-1] if fo>0 else 0.0); pos[fo]=max(0,rem); pos[fo+1:]=0
        pnl=float((pos*pn).sum())
        trades.append((d,int((pos>0).sum()),pnl,float(pos.sum()),dr_,pn,pos,zt,dd["yr"][0]))
        capital*=(1+pnl); equity.append(capital)
    return np.array(equity),trades
eq,tr=run()
pickle.dump({"eq":eq,"tr":tr},open("v8_full.pkl","wb"))
dts=pd.DatetimeIndex([pd.Timestamp(x) for x in dates])
cagr=(eq[-1]/CAPITAL)**(1/YEARS)-1
rmax=np.maximum.accumulate(eq); mdd=((eq-rmax)/rmax).min(); mi=int(np.argmin((eq-rmax)/rmax))
dr=np.diff(eq)/eq[:-1]; drn=dr[dr!=0]; sh=drn.mean()/drn.std()*np.sqrt(252)
pd_=[t for t in tr if t[1]>0]
tp=np.concatenate([t[6] for t in tr]); tp=tp[tp>0]
wp=np.concatenate([t[6][t[5]>0] for t in tr]); lp=np.concatenate([t[6][t[5]<=0] for t in tr])
allp=np.concatenate([t[5][t[6]>0] for t in tr])
print("="*104)
print("  GAP FADE v8  |  v6 + 分點因子(SHORT) + 曝險依預測品質排序")
print("  450萬・整張・零融資・成本0.109%/邊")
print("="*104)
print(f"  CAGR            {cagr*100:>8.1f}%")
print(f"  MDD             {mdd*100:>8.2f}%   (peak {dts[max(mi-1,0)].date()} -> trough {dts[mi].date()})")
print(f"  Sharpe          {sh:>8.2f}")
print(f"  Final equity    {eq[-1]/10000:>10,.0f} 萬   ({eq[-1]/CAPITAL:,.0f}x)")
print(f"  Period          {dts[0].date()} ~ {dts[-1].date()}  ({YEARS:.1f} years)")
print(f"  Trading days    {len(pd_):,} / {len(dates):,}   ({100*len(pd_)/len(dates):.0f}%)")
print(f"  Trades          {sum(t[1] for t in tr):,}   avg {np.mean([t[1] for t in pd_]):.1f}/active day")
print(f"  Positive days   {100*np.mean([t[2]>0 for t in pd_]):.1f}%")
print(f"  Avg day return  {np.mean([t[2] for t in pd_])*100:+.3f}%")
print(f"  Avg exposure    {np.mean([t[3] for t in pd_])*100:.1f}%   max {max(t[3] for t in tr)*100:.0f}%")
print(f"  Avg position    {tp.mean()*100:.2f}% of equity   max {tp.max()*100:.1f}%")
print(f"  Per-trade PnL   avg {100*allp.mean():+.3f}%   win {100*(allp>0).mean():.1f}%")
print(f"  Avg win/loss    {100*np.mean([p for p,w in zip(allp,wp)]):+.2f}% / {100*np.mean([p for p,w in zip(allp,lp)]):+.2f}%")
print(f"  Profit factor   {abs(wp.sum()/lp.sum()):.2f}")
print("\n"+"="*104); print("  逐年績效"); print("="*104)
print(f"{'年':<6}{'報酬%':>9}{'年內MDD%':>10}{'交易筆':>9}{'勝率%':>8}{'均PnL%':>9}{'均筆/日':>9}{'觸板停損%':>11}")
print("-"*74)
for y in range(2010,2027):
    idx=[i for i,t in enumerate(tr) if t[8]==y]
    if not idx: continue
    i0,i1=idx[0],idx[-1]+1
    seg=eq[i0:i1]; ret=(seg[-1]/seg[0]-1)*100
    rmx=np.maximum.accumulate(seg); ym=((seg-rmx)/rmx).min()*100
    n=sum(t[1] for t in tr[i0:i1]); act=[t for t in tr[i0:i1] if t[1]>0]
    P=np.concatenate([t[5][t[6]>0] for t in tr[i0:i1]]); W=np.concatenate([t[6][t[5]>0] for t in tr[i0:i1]])
    zt=np.concatenate([t[7][t[6]>0] for t in tr[i0:i1]]); Pz=np.concatenate([t[5][t[6]>0] for t in tr[i0:i1]])
    zstop=100*np.mean((Pz<0)&zt)
    print(f"{y:<6}{ret:>8.1f}{ym:>10.1f}{n:>9,}{100*(P>0).mean():>8.1f}{100*P.mean():>9.2f}{n/max(len(act),1):>9.1f}{zstop:>11.1f}")
print("\n"+"="*104); print("  逐月績效（%）"); print("="*104)
s=pd.Series(eq); i=dts[:len(eq)-1]
mo=s.iloc[1:].groupby([i.year,i.month]).last()
pv=np.r_[eq[0],mo.values[:-1]]; mm=(mo.values/pv-1)*100
print("  "+ "年    "+" ".join(f"{m:>6}" for m in range(1,13))+"    全年")
yr=None
for (y,mth),v in zip(mo.index,mm):
    if y!=yr:
        if yr is not None: print()
        print(f"  {y}  ",end=""); yr=y
    print(f"{v:>6.1f}",end="")
print()
print("\n  月度統計: 正報酬 {}/{} ({:.1f}%)   最差月 {:+.2f}%   月均 {:+.2f}%".format(
    (mm>0).sum(),len(mm),100*(mm>0).mean(),mm.min(),mm.mean()))
print("\n"+"="*104); print("  滾動期間穩定性"); print("="*104)
for w,lab in [(21,"3個月"),(63,"6個月"),(126,"12個月"),(252,"24個月"),(504,"48個月")]:
    r=(s/s.shift(w)-1).dropna()
    print(f"  {lab:<6} 樣本 {len(r):>5,}   正報酬 {100*(r>0).mean():>5.1f}%   最差 {100*r.min():>+7.2f}%   中位 {100*r.median():>+7.2f}%")
print("\n  日損益分佈: 最差 {:+.2f}%   P1 {:+.2f}%   中位 {:+.3f}%   P99 {:+.2f}%".format(
    100*min(t[2] for t in pd_),100*np.percentile([t[2] for t in pd_],1),
    100*np.median([t[2] for t in pd_]),100*np.percentile([t[2] for t in pd_],99)))
