# -*- coding: utf-8 -*-
r"""The SHORT gap ceiling, on the config live actually runs.

v19_gap2.py and v19_pinsens.py swept the ceiling on G - no stop loss - because
that is the configuration that clears the target. It is NOT what ships. Live runs
A: a 4 pct stop, capped by the price limit, with the 50/25 brake. And the reason
0.04 was chosen in the first place is a stop argument: a large gap puts the
limit-stop closer to the limit than to the entry, so the limit itself becomes the
exit (gap_fade_auto.py:516-523).

That argument can only be true with a stop armed. So the ceiling has to be
re-measured with the stop ON before anything is changed in live, or the change
would be justified by a configuration the account does not run.

The old table those comments quote (0.03 -3.71 ... 0.06 -5.31) was produced by
the backtest whose second brake tier never fired, so it is not evidence any more.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import v13_target as T

CAP = T.CAP0
BRAKE = ((-0.006, .50), (-0.012, .25))
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00, order_cap=30,
            cost_mode="measured", gap_max_long=0.08, spread=0.00105,
            nosl=False, brake=BRAKE)
PINS = [("平均 0.747", 0.00747), ("3-4% 實測 1.275", 0.01275)]
CAPS = [("0.03", 0.03), ("0.04 現行", 0.04), ("0.05", 0.05), ("0.06", 0.06),
        ("0.08", 0.08), ("無上限", None)]

HDR = "%-14s %-18s %+6s %+8s %+8s %7s %7s %6s %6s" % (
    "SHORT 上限", "鎖價成本", "13yr", "2014-21", "2022-26", "MDD", "最差年", "停損%", "筆/日")
rows = []
print("A 組：有 4% 停損、煞車 50/25（live 現在跑的就是這個）", flush=True)
print(HDR, flush=True)
for cap_tag, cap in CAPS:
    for pin_tag, pin in PINS:
        y = T.run(**dict(base, gap_max=cap, pin_penalty=pin, capture=True))
        yr = y["yearly"]; ks = sorted(yr)
        v = [yr[k] / CAP * 100 for k in ks]

        def avg(a, b):
            s = [x for k, x in zip(ks, v) if a <= k <= b]
            return sum(s) / len(s)
        tr = pd.DataFrame([dict(zip("date code dir notional gross reason entry exit".split(), t))
                           for t in y["trades"]])
        stopped = ((~tr["reason"].str.startswith("13:25"))
                   & (~tr["reason"].str.contains("TP"))).mean() * 100
        a, o, r, m, w = (sum(v) / len(v), avg(2014, 2021), avg(2022, 2026),
                         y["mdd"], min(v))
        flag = "  <== 達標" if (m >= -5.0 and r >= 100.0) else ""
        print("%-14s %-18s %+6.1f%% %+8.1f%% %+8.1f%% %6.2f%% %+6.1f%% %5.1f%% %6.1f%s"
              % (cap_tag, pin_tag, a, o, r, m, w, stopped, y["per_day"], flag), flush=True)
        rows.append(dict(cap=cap_tag, pin=pin_tag, all=a, old=o, recent=r, mdd=m,
                         worst=w, stopped=stopped, per_day=y["per_day"]))
    print(flush=True)
pd.DataFrame(rows).to_csv("_cap_sl.csv", index=False)
print("saved _cap_sl.csv", flush=True)
