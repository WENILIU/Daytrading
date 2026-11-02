# -*- coding: utf-8 -*-
r"""Fill the unused MDD budget: scale the HIGH-RATIO configs, not the default one.

The armgrid ceiling is +91.4 pct at -4.74 (gap .04/oc22) and the best RATIO is
gap .03/oc20 at +87.0 pct but only -3.98 MDD (ratio 21.8). That config leaves
1.0 pp of the -5 pct budget unused. The earlier "scale is pure leverage" result was
measured on the DEFAULT config, whose p90 exposure is already 99.4 pct - scale had
no room there. These tighter configs deploy less, so scale is NOT the same test.

Target ratio is 20.0. If scaling the 21.8-ratio config up to MDD -5 pct keeps ratio
>= 20, it lands at 100 pct. This is the last point in the space.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00,
            gap_max_long=0.08, spread=0.00105,
            nosl=True, brake=((-0.008, .50), (-0.016, .25)))
CFG = [(0.030, 20), (0.030, 22), (0.040, 22)]
SCALES = [1.0, 1.15, 1.30, 1.45]
MODES = ["auction", "measured"]

HDR = "%-26s %+8s %7s %7s %6s %6s" % ("cfg mode scale", "2022-26", "MDD", "比值", "p90", "筆/日")
rows = []
print(HDR, flush=True)
for cap, oc in CFG:
    for mode in MODES:
        for sc in SCALES:
            y = T.run(**dict(base, cost_mode=mode, gap_max=cap, order_cap=oc, size_scale=sc))
            yr = y["yearly"]; ks = sorted(yr)
            v = [yr[k] / CAP * 100 for k in ks]
            r = sum(x for k, x in zip(ks, v) if 2022 <= k <= 2026) / len([k for k in ks if 2022 <= k <= 2026])
            m = y["mdd"]; ratio = r / abs(m)
            p90 = y.get("expo_pct", {}).get("p90", float("nan"))
            flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ("  <- MDD內" if m >= -5.0 else "")
            print("g%.3f oc%d %-9s x%.2f  %+8.1f%% %7.2f%% %6.1f %6.1f %6.1f%s"
                  % (cap, oc, mode, sc, r, m, ratio, p90, y["per_day"], flag), flush=True)
            rows.append(dict(gap_max=cap, order_cap=oc, mode=mode, scale=sc, recent=r,
                             mdd=m, ratio=ratio, p90=p90, per_day=y["per_day"]))
df = pd.DataFrame(rows); df.to_csv("_scale_fill.csv", index=False)
ok = df[df.mdd >= -5.0].sort_values("recent", ascending=False)
print("\n--- MDD 在 -5%% 內按近五年報酬排序（目標 100%%）---", flush=True)
print(ok[["gap_max","order_cap","mode","scale","recent","mdd","ratio","p90"]].to_string(index=False), flush=True)
if len(ok):
    b = ok.iloc[0]
    print("\n最高近五年報酬（MDD 內）：%.1f%% @ g%.3f oc%d %s x%.2f，MDD %.2f%%，比值 %.1f"
          % (b.recent, b.gap_max, b.order_cap, b.mode, b.scale, b.mdd, b.ratio), flush=True)
    print("距離目標：%.1f pp" % (100.0 - b.recent), flush=True)
print("saved _scale_fill.csv", flush=True)
