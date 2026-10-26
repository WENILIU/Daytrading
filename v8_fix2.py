import pandas as pd, numpy as np, pickle, warnings; warnings.filterwarnings("ignore")
D=pickle.load(open("v8_full.pkl","rb")); tr=D["tr"]
gp=gl=0.0; WP=[]; WL=[]; CONTR=[]
for t in tr:
    p,w=t[5],t[6]; m=w>0
    pw=p[m]; ww=w[m]
    gp+=(pw[pp>0]*ww[pp>0]).sum() if False else (pw[pw>0]*ww[pw>0]).sum()
    gl+=(pw[pw<0]*ww[pw<0]).sum()
    WP.append(pw[pw>0]); WL.append(pw[pw<0]); CONTR.append(pw*ww)
WP=np.concatenate(WP); WL=np.concatenate(WL); CT=np.concatenate(CONTR)
print("  加權獲利因子 (毛利/毛損)        %.2f"%(gp/abs(gl)))
print("  成交筆數                       %s   勝率 %.1f%%"%(f"{len(WP)+len(WL):,}",100*len(WP)/(len(WP)+len(WL))))
print("  平均每筆盈 %+.2f%% (%s 筆)   平均每筆虧 %+.2f%% (%s 筆)"%(
    100*WP.mean(),f"{len(WP):,}",100*WL.mean(),f"{len(WL):,}"))
print("  盈虧比                         %.2f"%abs(WP.mean()/WL.mean()))
print("  期望值/筆                      %+.3f%%"%(100*(gp+gl)/ (len(WP)+len(WL)) / (CT.sum()/ (len(WP)+len(WL)) * 0 + 1) * 0 + 100*np.mean(np.concatenate([t[5][t[6]>0] for t in tr]))))
print("  最大單筆盈 %+.2f%%   最大單筆虧 %+.2f%%"%(100*WP.max(),100*WL.min()))
print("  加權後每日平均貢獻              %+.4f%% of equity"%(100*CT.sum()/len(tr)))
