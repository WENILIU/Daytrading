import sys, pandas as pd, numpy as np
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0,".")
from gap_fade_auto import calc_price_limits, calc_effective_sl, snap_to_valid_price, get_tick_size, Direction
df=pd.read_csv(r"D:\AI專案\StockAgent\DayTrading\daytrading.csv", encoding="utf-8-sig")
def valid(p):
    t=get_tick_size(p); return abs(p/t-round(p/t))<1e-9
bad_sl=bad_tp=bad_lim=0; ex=[]
for _,r in df.iterrows():
    e=float(r["進場價"]); pc=float(r["前收"]); sh=(r["方向"]=="SHORT")
    d=Direction.SHORT if sh else Direction.LONG
    sl,_,_=calc_effective_sl(e,pc,d,0.04)
    tp_pct=0.20 if float(r["停利TP%"])>=0.2 else 0.12
    tp=snap_to_valid_price(e*(1-tp_pct)) if sh else snap_to_valid_price(e*(1+tp_pct))
    lu,ld=calc_price_limits(pc)
    for p,tag in ((sl,"SL"),(tp,"TP"),(lu,"LU"),(ld,"LD")):
        if not valid(p):
            bad_sl+= (tag=="SL"); bad_tp+= (tag=="TP"); bad_lim+= tag in ("LU","LD")
            if len(ex)<5: ex.append((r["日期"],r["股票"],tag,p))
    if sh and not (sl<=lu): 
        ex.append(("SL>LU",r["日期"],r["股票"],sl,lu))
print(f"檢查 {len(df)} 筆的 SL/TP/漲停/跌停 合法性: SL 違規 {bad_sl}, TP 違規 {bad_tp}, 漲跌停 違規 {bad_lim}")
for x in ex[:6]: print("  ",x)
# 與回測存的值對照（回測未 snap，應只差半個價差內）
d=[]
for _,r in df.iterrows():
    e=float(r["進場價"]); pc=float(r["前收"]); sh=(r["方向"]=="SHORT")
    sl,_,_=calc_effective_sl(e,pc,Direction.SHORT if sh else Direction.LONG,0.04)
    d.append(abs(sl-float(r["停損價"]))/e*100)
d=np.array(d)
print(f"即時 SL 與回測 SL 差異: 平均 {d.mean():.4f}%  最大 {d.max():.4f}%")
print("PASS 全部合法" if bad_sl==bad_tp==bad_lim==0 else "FAIL")
