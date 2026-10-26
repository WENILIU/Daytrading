import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
exec(open("fast_nm.py").read().split("print(\"=\"*60)")[0])
O=pd.read_pickle("order_test.pkl")
d=pd.DatetimeIndex([pd.Timestamp(x) for x in dates])
def seg(eq,y0,y1):
    i0=int(np.searchsorted(d.values,np.datetime64(f"{y0}-01-01")))
    i1=min(int(np.searchsorted(d.values,np.datetime64(f"{y1+1}-01-01"))),len(eq)-1)
    return eq[i0:i1],i0,i1
def stv(eq,y0,y1):
    s,i0,i1=seg(eq,y0,y1)
    if len(s)<50: return None
    yrs=(d[min(i1-1,len(d)-1)]-d[i0]).days/365.25
    r=(s[-1]/s[0])**(1/yrs)-1
    rmx=np.maximum.accumulate(s); m=((s-rmx)/rmx).min()
    return r*100,m*100
V6=O["v6 現行(原順序)"]; V8=O["v7 +按預測排序"]
print("="*92); print("  v8 = v6 + 分點因子(SHORT) + 曝險按預測品質排序"); print("="*92)
c,m=stv(V6,2010,2026); print(f"  v6 基準:  CAGR {c:>6.1f}%  MDD {m:>6.2f}%")
c,m=stv(V8,2010,2026); print(f"  v8 新版:  CAGR {c:>6.1f}%  MDD {m:>6.2f}%   終值 {V8[-1]/1e8:,.0f} 億")
print("\n  逐年:")
print(f"  {'年':<6}{'v6 %':>9}{'v8 %':>9}{'Δ':>8}{'v6 MDD':>9}{'v8 MDD':>9}")
pos=0; tot=[]
for y in range(2010,2027):
    a=stv(V6,y,y); b=stv(V8,y,y)
    if a is None or b is None: continue
    tot.append(b[0]-a[0])
    if b[0]-a[0]>0: pos+=1
    print(f"  {y:<6}{a[0]:>8.1f}%{b[0]:>8.1f}%{b[0]-a[0]:>+7.1f}%{a[1]:>8.1f}%{b[1]:>8.1f}%")
print(f"\n  v8 優於 v6 的年份: {pos}/{len(tot)}   平均年增益 {np.mean(tot):+.1f}pp")
print("\n  Rolling 12M 最差情境（v8）:")
for w,lab in [(21,"3M"),(126,"6M"),(252,"12M")]:
    s=pd.Series(V8); r=(s/s.shift(w)-1).dropna()
    print(f"    {lab:<5} 正報酬 {100*(r>0).mean():>5.1f}%   最差 {100*r.min():>+7.2f}%")
print("\n  月度（v8，%）:")
s=pd.Series(V8); i=pd.DatetimeIndex(d[:len(V8)-1])
mo=s.iloc[1:].groupby([i.year,i.month]).last()
prev=pd.Series([V8[0]]+list(mo.values[:-1]))
mm=(mo.values/prev.values-1)*100
yr=None
for (y,mth),v in zip(mo.index,mm):
    if y!=yr: print(); print(f"  {y}: ",end=""); yr=y
    print(f"{v:>6.1f}",end="")
print()
