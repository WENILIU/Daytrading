# -*- coding: utf-8 -*-
r"""Per-window drawdown for the lock filter.

The lock filter's only surviving claim is that it lowers MDD, but run() reports a single
full-period number, so that claim has no out-of-sample support yet. The daily book is
reconstructable from the captured trades using the same rule the engine uses (book capped
at 450 萬, excess withdrawn, drawdown measured against the running peak of the position
book). With that, the drawdown can be measured inside 2014-2021 and inside 2022-2026
separately, which is the test the return numbers could not settle.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

CAP = T.CAP0
PIN = 0.03149 + 0.0015 + 0.30 * 2 / 365.0
base = dict(liq=0.10, slip_scale=1.0, gap_scale=1.0, exposure=1.00,
            gap_max_long=0.08, spread=0.00105, cost_mode="measured",
            brake=((-0.008, .50), (-0.016, .25)), gap_max=0.040, order_cap=20,
            nosl=True, pin_short=PIN, pin_long=0.0)
D0 = T.D.copy()
D0["zc"] = pd.to_numeric(D0["zt_close_60"], errors="coerce").fillna(0.0)
ORIG_GROUPS = T.GROUPS
WINS = {"2014-2021": ("2014-01-01", "2021-12-31"), "2022-2026": ("2022-01-01", "2026-12-31")}

def lock(K):
    D = D0.copy()
    D["lock_rate_up_250"] = np.where(D["direction"] == "SHORT", D["zc"] / 60.0, np.nan)
    D["lock_rate_dn_250"] = 0.0
    T.D = D
    T.GROUPS = {d: g[~g["blocked"]] for d, g in D.groupby("date")}

def windowed_mdd(trades):
    """Rebuild the position book day by day, then measure drawdown inside each window."""
    daily = {}
    for d, _c, _dir, notional, gross, *_ in trades:
        daily[pd.Timestamp(d)] = daily.get(pd.Timestamp(d), 0.0) + notional * gross
    out = {}
    for name, (a, b) in WINS.items():
        book = peak = CAP
        worst = 0.0
        for d in sorted(daily):
            if not (pd.Timestamp(a) <= d <= pd.Timestamp(b)):
                continue
            book += daily[d]
            if book > CAP:
                book = CAP
            peak = max(peak, book)
            worst = min(worst, (book - peak) / peak)
        out[name] = worst * 100
    return out

rows = []
for tag, setup, cfg in [("honest B (基準)", lambda: setattr(T, "GROUPS", ORIG_GROUPS), base),
                        ("lock zt60 > 6", lambda: lock(6), dict(base, max_lock_rate=6 / 60.0)),
                        ("lock zt60 > 3", lambda: lock(3), dict(base, max_lock_rate=3 / 60.0))]:
    setup()
    y = T.run(**dict(cfg, capture=True))
    w = windowed_mdd(y["trades"])
    print("%-16s 全期MDD %6.2f%% | 2014-21 MDD %6.2f%% | 2022-26 MDD %6.2f%%"
          % (tag, y["mdd"], w["2014-2021"], w["2022-2026"]), flush=True)
    rows.append(dict(tag=tag, mdd_all=y["mdd"], **w))
T.GROUPS = ORIG_GROUPS
pd.DataFrame(rows).to_csv("_lockmdd.csv", index=False)
print("saved _lockmdd.csv", flush=True)
