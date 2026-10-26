import pandas as pd, numpy as np, warnings; warnings.filterwarnings("ignore")
exec(open("v8_cost2.py",encoding="utf-8-sig").read().split("res={}")[0])
res={}
for cost in [0.00109,0.00235]:
    D=build(cost); eq,tr=run(D)
    e=pd.Series(eq[1:],index=pd.to_datetime([t[0] for t in tr]))
    T=pd.DataFrame(tr,columns=["date","pnl","n","expo","avgpnl","win","ntot"]); T["date"]=pd.to_datetime(T["date"]); T["year"]=T["date"].dt.year
    res[cost]=(e,T)
print("年     [成本0.109%/邊]              |  [成本0.235%/邊 = 2.15倍]")
print("      報酬%   MDD%  勝率% 均PnL%   |  報酬%   MDD%  勝率% 均PnL%")
for y in range(2010,2027):
    out=[]
    for cost in [0.00109,0.00235]:
        e,T=res[cost]
        s=e.loc[str(y)]
        prev=e[e.index.year==y-1].iloc[-1] if y>2010 else CAPITAL
        ret=s.iloc[-1]/prev-1
        mdd=((s-s.cummax())/s.cummax()).min()
        t=T[T["year"]==y]
        wr=t["win"].sum()/t["ntot"].sum()*100
        ap=t["avgpnl"].mean()*100
        out.append((ret*100,mdd*100,wr,ap))
    print(f"{y}  {out[0][0]:7.1f} {out[0][1]:6.1f} {out[0][2]:5.1f} {out[0][3]:6.2f}   | {out[1][0]:7.1f} {out[1][1]:6.1f} {out[1][2]:5.1f} {out[1][3]:6.2f}")
for cost in [0.00109,0.00235]:
    e,T=res[cost]
    r=e.pct_change().fillna(0); yrs=(e.index[-1]-e.index[0]).days/365.25
    cg=(e.iloc[-1]/e.iloc[0])**(1/yrs)-1; dd=((e-e.cummax())/e.cummax()).min()
    print(f"\ncost {cost*100:.3f}%/side  CAGR {cg*100:.1f}%  MDD {dd*100:.2f}%  Sharpe {r.mean()/r.std()*np.sqrt(243):.2f}")
