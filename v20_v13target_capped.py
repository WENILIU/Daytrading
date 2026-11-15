import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

DMIN = "2023-05-23"
BASE = T.D[(pd.to_datetime(T.D["date"]) >= pd.Timestamp(DMIN)) & (~T.D["blocked"].values)]

def run_cfg(s3_th, qmin, dir_cap, brake, ss):
    Dw = BASE[BASE["pred_q"] >= qmin]
    Dw = Dw[Dw["price_dir"] < s3_th]   # S3 gate at threshold s3_th
    T.GROUPS = {d: g for d, g in Dw.groupby("date")}
    T.days = sorted(Dw["date"].unique())
    r = T.run(slip_scale=1.0, date_min=DMIN, s3=False, size_scale=ss,
              exposure=1.0, dir_cap=dir_cap, brake=brake)
    yrs = sorted(r["yearly"]); rets = [r["yearly"][k]/T.CAP0*100 for k in yrs]
    return r, yrs, rets, len(Dw)

BRAKES = {
    "std": ((-0.03, 0.30), (-0.06, 0.12)),
    "tight": ((-0.012, 0.50), (-0.024, 0.20)),
    "vtight": ((-0.008, 0.60), (-0.016, 0.30)),
}
rows = []
for th in [-0.005, -0.008]:
    for qmin in [0.20, 0.40]:
        for dc in [None, 0.5, 0.4]:
            for bkey, brake in BRAKES.items():
                for ss in [1.0, 1.2, 1.4, 1.6]:
                    r, yrs, rets, n = run_cfg(th, qmin, dc, brake, ss)
                    an = np.mean(rets); md = r["mdd"]
                    ok = (an >= 200 and md >= -5.0)
                    rows.append(dict(ok=ok, an=an, md=md, cal=(abs(an/md) if md<-0.01 else 99),
                                     th=th, qmin=qmin, dc=dc, br=bkey, ss=ss,
                                     per=r["per_day"], exm=r["expo_max"], n=n))

ok_rows = sorted([x for x in rows if x["ok"]], key=lambda x: -x["an"])
print("exposure=1.0（無借錢，450萬硬上限）下符合 年均>=200%% 且 部位MDD>=-5%%：%d / %d" % (len(ok_rows), len(rows)))
print("%-7s %-6s %-6s %-7s %-5s %8s %9s %7s %7s" %
      ("s3_th","qmin","dir_cap","brake","size","年均%","部位MDD%","calmar","筆/日"))
for x in ok_rows[:15]:
    print("%-7.1f%% %-6s %-6s %-7s %-5.1f %8.1f %9.2f %7.1f %7.1f" %
          (x["th"]*100, x["qmin"], x["dc"], x["br"], x["ss"], x["an"], x["md"], x["cal"], x["per"]))

print()
print("=== 無借錢上限下最佳 calmar（前 15）===")
rows.sort(key=lambda x: -x["cal"])
for x in rows[:15]:
    tag = "  <== 達標" if x["ok"] else ""
    print("th=%-6.1f%% q=%-4s dir_cap=%-5s %-7s size=%-4.1f 年均%+6.1f%% MDD%+6.2f%% calmar%5.1f 筆/日%4.1f%s" %
          (x["th"]*100, x["qmin"], x["dc"], x["br"], x["ss"], x["an"], x["md"], x["cal"], x["per"], tag))
