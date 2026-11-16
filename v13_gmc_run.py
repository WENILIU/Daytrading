import os
for k in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"]: os.environ[k]="1"
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import v13_target as V
CAP=V.CAP0
def show(label,**cfg):
    cfg.setdefault("slip_scale",1.0); cfg.setdefault("exposure",1.0); cfg.setdefault("date_min","2023-05-23")
    r=V.run(**cfg); y=r["yearly"]; yrs=sorted(y); rets=[y[k]/CAP*100 for k in yrs]
    print("  %-24s MDD %+6.2f%%  年均 %+6.1f%%  最差年 %+6.1f%%  筆/日 %4.1f  曝險 %5.1f%%"%(
        label,r["mdd"],np.mean(rets),min(rets),r["per_day"],r["expo"]),flush=True)
    print("      逐年："," ".join("%d %+.0f"%(k,v) for k,v in zip(yrs,rets)),flush=True)
    return r
print("="*120); print("釘450萬/獲利出金/slip1.00/不借錢/2023-05起"); print("="*120)
show("現行(現行book)",s3=False)
show("S3(s3=True)",s3=True)
show("隔日沖gmc(空腿)",gmc=True)
show("S3+隔日沖",s3=True,gmc=True)
