import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T   # heavy: builds 2014-2026 book at import

DMIN = "2023-05-23"
# coverage diagnostics on the restricted window
D = T.D
Dw = D[pd.to_datetime(D["date"]) >= pd.Timestamp(DMIN)]
cov = Dw["price_dir"].notna().sum()
print("=== 1-min coverage in %s+ ===" % DMIN)
print("  signals %d, 1-min covered %d (%.0f%%), s3_pass(dropped>0.5%%) %d" %
      (len(Dw), cov, 100*cov/max(len(Dw),1), int(Dw["s3_pass"].sum())))
print()

def show(tag, **cfg):
    r = T.run(date_min=DMIN, slip_scale=1.0, **cfg)
    y = r["yearly"]; yrs = sorted(y); rets = [y[k]/T.CAP0*100 for k in yrs]
    print("  %-34s 部位MDD %+6.2f%%  年均 %+7.1f%%  中位 %+7.1f%%  最差年 %+7.1f%%  筆/日 %4.1f  曝險 %5.1f%%" %
          (tag, r["mdd"], np.mean(rets), np.median(rets), min(rets), r["per_day"], r["expo"]))
    print("      逐年%：", " ".join("%d %+.0f" % (k, v) for k, v in zip(yrs, rets)))
    return r

print("="*130)
print("2023-05+ 對照組（釘在 450 萬、獲利出金；slip_scale=1.00 = 09:01 進場實測成本）")
print("="*130)
b = show("v13 現行 (無 S3)", liq=0.25)
s = show("v13 + S3 竭盡過濾", liq=0.25, s3=True)
print()
print("delta: 筆/日 %.1f -> %.1f ; 年均 %+.1f%% -> %+.1f%% ; 部位MDD %+.2f%% -> %+.2f%%" %
      (b["per_day"], s["per_day"],
       np.mean([b["yearly"][k]/T.CAP0*100 for k in sorted(b["yearly"])]),
       np.mean([s["yearly"][k]/T.CAP0*100 for k in sorted(s["yearly"])]),
       b["mdd"], s["mdd"]))
