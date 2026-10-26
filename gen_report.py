import sys, numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
import v13_engine as E
cv,got,_=E.run_backtest(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
sa=E.stats(cv["A_pnl"]); sc=E.stats(cv["C_pnl"])
L=[]; w=L.append
w("Gap Fade v13 - V6 完整績效（漲停價規則 + 停損/停利價合法化 + 漲停-1價浮點比較修正後重訓）")
w("產生時間 2026-10-27   引擎 v13_engine.run_backtest(kmode='one', tmode='on', min_weight=0.005, min_range=0.001)")
w("成本 0.109%/邊(手續費 1.7 折、無借券費)、一律整張、零融資")
w("="*96)
w("")
w("A = 策略設計面（複利、無整張限制）    C = 450 萬固定資金 + 一律整張（你實務能做的）")
w(f"  A: CAGR {sa['cagr']:.1f}%  MDD {sa['mdd']:.2f}%  Sharpe {sa['sharpe']:.2f}  Calmar {sa['calmar']:.1f}  {cv['A_n'].mean():.1f} 筆/日  平均曝險 {cv['A_expo'].mean()*100:.1f}%")
w(f"  C: CAGR {sc['cagr']:.1f}%  MDD {sc['mdd']:.2f}%  Sharpe {sc['sharpe']:.2f}  Calmar {sc['calmar']:.1f}  {cv['C_n'].mean():.1f} 筆/日  平均曝險 {cv['C_expo'].mean()*100:.1f}%")
w("")
w("【四次重訓的數字穩定性 — 同一組策略參數，只差程式修正】")
w("  V4 修正前:            A 180.4% / -3.39%   C 170.4% / -3.33%")
w("  V5 中間(只修漲停):     A 191.0% / -3.32%   C 171.6% / -4.83%")
w("  V5 (停損價合法化):      A 191.5% / -3.29%   C 174.2% / -3.63%")
w(f"  V6 (浮點比較修正):      A {sa['cagr']:.1f}% / {sa['mdd']:.2f}%   C {sc['cagr']:.1f}% / {sc['mdd']:.2f}%")
w("  V6 修的是 lu-tk 的浮點誤差(43.85-0.05=43.800000000000004)，讓 165 筆 SHORT 訊號")
w("  在「高點剛好等於漲停-1價」時漏掉停損 -> 回測偏樂觀。修正後數字下降是正確的。")
w("  => CAGR 與 MDD 的點估計不可信。規劃資金請用保守端: CAGR 165%, MDD -5%。")
w("     跨重訓穩定: Sharpe 5.4-5.5、逐年全正、Rolling 6M/12M 100% 正。")
w("")
w("【逐年】")
w(f"{'年':>6} {'交易日':>6} {'A筆/日':>7} {'C筆/日':>7} {'A年報酬%':>9} {'C年報酬%':>9} {'C年MDD%':>8} {'A曝險%':>7} {'C曝險%':>7}")
for yr in sorted(set(cv.index.year)):
    m=cv.index.year==yr; sub=cv[m]
    a=(1+sub["A_pnl"]).prod()-1; c=(1+sub["C_pnl"]).prod()-1
    e=(1+sub["C_pnl"]).cumprod(); cm=((e-e.cummax())/e.cummax()).min()*100
    w(f"{yr:>6} {int(m.sum()):>6} {sub['A_n'].mean():>7.1f} {sub['C_n'].mean():>7.1f} {a*100:>9.1f} {c*100:>9.1f} {cm:>8.1f} {sub['A_expo'].mean()*100:>7.1f} {sub['C_expo'].mean()*100:>7.1f}")
def stab(tag,s):
    mm=s.groupby(pd.PeriodIndex(s.index,freq="M")).apply(lambda x:(1+x).prod()-1)*100
    e=(1+s).cumprod()
    out=[f"【{tag} 穩定度】正報酬月 {int((mm>0).sum())}/{len(mm)}  最差月 {mm.min():.2f}%  月均 {mm.mean():.2f}%"]
    for k,lab in [(63,"3M"),(126,"6M"),(252,"12M")]:
        r=(e/e.shift(k)-1).dropna()
        out.append(f"   Rolling {lab:<5} 正報酬 {(r>0).mean()*100:5.1f}%  最差 {r.min()*100:+.2f}%")
    return out
for ln in stab("A",cv["A_pnl"])+stab("C",cv["C_pnl"]): w(ln)
w("")
w("【逐月 C 450萬 報酬%】")
c=cv["C_pnl"]; mp=c.groupby(pd.PeriodIndex(c.index,freq="M")).apply(lambda x:(1+x).prod()-1)*100
piv=pd.DataFrame({"y":[str(x)[:4] for x in mp.index],"m":[str(x)[5:7] for x in mp.index],"v":mp.values}).pivot_table(index="y",columns="m",values="v")
piv.columns=[int(x) for x in piv.columns]
w(piv.round(1).to_string())
txt="\n".join(L)
open("final_report_v6.txt","w",encoding="utf-8").write(txt)
import shutil; shutil.copy("final_report_v6.txt", r"D:\AI專案\StockAgent\DayTrading\final_report.txt")
print(txt[:1500]); print("...\nSAVED final_report_v6.txt + copied to D:")
