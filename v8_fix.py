import pandas as pd, numpy as np, pickle, warnings; warnings.filterwarnings("ignore")
D=pickle.load(open("v8_full.pkl","rb")); tr=D["tr"]
gp=[];gl=[];wp=[];wl=[]
for t in tr:
    p,w=t[5],t[6]
    m=w>0
    gp.append((p[m]*w[m]).sum()); gl.append((p[~m]*w[~m]).sum())
    wp.append(p[m]); wl.append(p[~m])
gp=np.array(gp).sum(); gl=np.array(gl).sum()
WP=np.concatenate(wp); WL=np.concatenate(wl)
print("  加權獲利因子 (gross profit / gross loss)  %.2f"%(gp/abs(gl)))
print("  平均每筆盈（未加權）  %+.2f%%   筆數 %s"%(100*WP.mean(),f"{len(WP):,}"))
print("  平均每筆虧（未加權）  %+.2f%%   筆數 %s"%(100*WL.mean(),f"{len(WL):,}"))
print("  盈虧比               %.2f"%(abs(WP.mean()/WL.mean())))
print("  期望值/筆            %+.3f%%"%(100*(WP.mean()*len(WP)+WL.mean()*len(WL))/(len(WP)+len(WL))))
print("  最大單筆虧           %+.2f%%   最大單筆盈 %+.2f%%"%(100*WL.min(),100*WP.max()))
print("  加權後單筆平均貢獻    %+.4f%% of equity"%(100*((np.concatenate([t[5][t[6]>0]*t[6][t[6]>0] for t in tr])).mean())))
