import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

DMIN = "2023-05-23"
DAY = pd.to_datetime(T.D["date"])
MASK23 = (DAY >= pd.Timestamp(DMIN)) & (~T.D["blocked"].values)

def run_cfg(qmin=None, use_s3=True, **kw):
    Dw = T.D[MASK23]
    if use_s3:
        Dw = Dw[Dw["s3_pass"]]
    if qmin is not None:
        Dw = Dw[Dw["pred_q"] >= qmin]
    T.GROUPS = {d: g for d, g in Dw.groupby("date")}
    T.days = sorted(Dw["date"].unique())
    r = T.run(slip_scale=1.0, date_min=DMIN, s3=False, **kw)
    yrs = sorted(r["yearly"]); rets = [r["yearly"][k]/T.CAP0*100 for k in yrs]
    cal = abs(np.mean(rets)/r["mdd"]) if r["mdd"] < -0.01 else 999
    return dict(annual=np.mean(rets), mdd=r["mdd"], per_day=r["per_day"],
                expo=r["expo"], expo_max=r["expo_max"], worst=min(rets),
                cal=cal, yr=rets, n=len(Dw))

print("=== STAGE 1: size_scale x exposure, s3=True (2023-05+, 全成本) ===")
print("%-8s %-9s %8s %9s %7s %8s %8s %s" % ("size","exposure","年均%","部位MDD%","calmar","筆/日","曝險max","達標"))
for ss in [1.0, 1.25, 1.5, 2.0, 2.5]:
    for ex in [1.0, 1.5, 2.0]:
        r = run_cfg(size_scale=ss, exposure=ex)
        ok = "OK" if (r["annual"] >= 200 and r["mdd"] >= -5.0) else ""
        print("%-8.2f %-9.1f %8.1f %9.2f %7.1f %8.1f %8.1f %s" %
              (ss, ex, r["annual"], r["mdd"], r["cal"], r["per_day"], r["expo_max"], ok))

print()
print("=== STAGE 2: + pred_q floor, + dir_cap, + tighter brake ===")
BRAKES = {
    "std": ((-0.03, 0.30), (-0.06, 0.12)),
    "tight": ((-0.015, 0.50), (-0.03, 0.20)),
}
rows = []
for qmin in [None, 0.20, 0.40]:
    for dc in [None, 0.5, 0.35]:
        for bkey, brake in BRAKES.items():
            for ss in [1.5, 2.0, 2.5, 3.0]:
                for ex in [1.0, 1.5]:
                    try:
                        r = run_cfg(qmin=qmin, use_s3=True, size_scale=ss,
                                    exposure=ex, dir_cap=dc, brake=brake)
                    except Exception as e:
                        continue
                    ok = (r["annual"] >= 200 and r["mdd"] >= -5.0)
                    rows.append((ok, r["annual"], r["mdd"], r["cal"], qmin, dc, bkey, ss, ex, r["per_day"], r["expo_max"]))
ok_rows = [x for x in rows if x[0]]
ok_rows.sort(key=lambda x: -x[1])
print("符合 年均>=200%% 且 部位MDD>=-5%%：%d / %d" % (len(ok_rows), len(rows)))
print("%-6s %-6s %-6s %-6s %6s %8s %9s %7s %8s %7s" %
      ("qmin","dir_cap","brake","size","expo","年均%","部位MDD%","calmar","筆/日","曝險max"))
for ok, an, md, cal, qmin, dc, bkey, ss, ex, pd_, exm in ok_rows[:20]:
    print("%-6s %-6s %-6s %-6.1f %6.1f %8.1f %9.2f %7.1f %8.1f %7.1f" %
          (qmin, dc, bkey, ss, ex, an, md, cal, pd_, exm))

print()
rows.sort(key=lambda x: -x[3])
print("=== 最佳 calmar（前 12，不限達標）===")
print("%-6s %-6s %-6s %-6s %6s %8s %9s %7s" %
      ("qmin","dir_cap","brake","size","expo","年均%","部位MDD%","calmar"))
for ok, an, md, cal, qmin, dc, bkey, ss, ex, pd_, exm in rows[:12]:
    print("%-6s %-6s %-6s %-6.1f %6.1f %8.1f %9.2f %7.1f" %
          (qmin, dc, bkey, ss, ex, an, md, cal))
