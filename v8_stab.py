import pandas as pd, numpy as np, warnings, pickle; warnings.filterwarnings("ignore")
exec(open("fast_nm.py").read().split("print(\"=\"*60)")[0])
O=pd.read_pickle("order_test.pkl")
d=pd.DatetimeIndex([pd.Timestamp(x) for x in dates])
print("="*96); print("  穩定性對照 v6 vs v8"); print("="*96)
print(f"  {'滾動區間':<10}{'v6 正報酬%':>12}{'v6 最差%':>10}{'v8 正報酬%':>12}{'v8 最差%':>10}")
for w,lab in [(21,"3個月"),(63,"6個月"),(126,"12個月"),(252,"24個月")]:
    out=[]
    for nm in ["v6 現行(原順序)","v7 +按預測排序"]:
        s=pd.Series(O[nm]); r=(s/s.shift(w)-1).dropna()
        out+=[100*(r>0).mean(),100*r.min()]
    print(f"  {lab:<10}{out[0]:>11.1f}%{out[1]:>9.2f}%{out[2]:>11.1f}%{out[3]:>9.2f}%")
print()
for nm in ["v6 現行(原順序)","v7 +按預測排序"]:
    s=pd.Series(O[nm]); i=d[:len(s)-1]
    dr=pd.Series(np.diff(s)/s[:-1])
    mo=s.iloc[1:].groupby([i.year,i.month]).last()
    pv=np.r_[s.iloc[0],mo.values[:-1]]; mm=(mo.values/pv-1)*100
    print(f"  {nm:<18} 月正報酬 {100*(mm>0).mean():>5.1f}% ({(mm>0).sum()}/{len(mm)})   日均 {dr[dr!=0].mean()*100:+.3f}%")
print("\n  務實預期（v8，半個年不年化）:")
for a,b in [(2023,2025),(2024,2025),(2026,2026)]:
    for nm in ["v6 現行(原順序)","v7 +按預測排序"]:
        eq=O[nm]; i0=int(np.searchsorted(d.values,np.datetime64(f"{a}-01-01")))
        i1=min(int(np.searchsorted(d.values,np.datetime64(f"{b+1}-01-01"))),len(eq)-1)
        seg=eq[i0:i1]
        yrs=(d[min(i1-1,len(d)-1)]-d[i0]).days/365.25
        if a==b and a==2026:
            print(f"    {a} 上半年（{yrs:.2f}年，不年化）: {nm:<18} {(seg[-1]/seg[0]-1)*100:>+8.1f}%")
        else:
            print(f"    {a}-{b}（{yrs:.1f}年）: {nm:<18} CAGR {((seg[-1]/seg[0])**(1/yrs)-1)*100:>7.1f}%")
