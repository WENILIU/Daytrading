# -*- coding: utf-8 -*-
r"""Is the "touched vs locked" question measurable at all?

The 100 pct target now hinges on one rule: stop when the price touches limit-up.
Relaxing it is worth +21 pct on 2022-2026, but daily bars cannot tell a touch that
released from a lock that held all day - and a lock cannot be exited at 13:25
either. So the rule can only be built from 1-minute data, and the first question
is coverage: of the trades the shipped book actually stops out on a limit, how many
have a 1-minute file on disk?

Availability is read from the folder layout the data lives in:
  <root>\<stock name>\1\<code>_YYYY-MM.json    a whole month
  <root>\<stock name>\1\<code>_YYYY-MM-DD.json a single day
Monthly files expand to every date in that month.
"""
import warnings; warnings.filterwarnings("ignore")
import os, re, json, calendar, collections
import pandas as pd
import v13_target as T
from v13_engine import exit_of_legal

IDX = pd.read_pickle("stock_1min_index.pkl")      # code -> folder holding "1"
MONTH = re.compile(r"^(\d+)_(\d{4})-(\d{2})\.json$")
DAY = re.compile(r"^(\d+)_(\d{4})-(\d{2})-(\d{2})\.json$")

avail = {}
if os.path.exists("_min1_avail.pkl"):
    avail = pd.read_pickle("_min1_avail.pkl")
else:
    for code, folder in IDX.items():
        # IDX already maps code -> the folder that holds the 1-minute files
        # (verified 2026-11-02: the value ends in "\1"), so joining "1" again
        # looked at a path that does not exist and found nothing.
        d1 = folder if os.path.isdir(folder) else os.path.join(folder, "1")
        if not os.path.isdir(d1):
            continue
        days = set()
        for fn in os.listdir(d1):
            m = DAY.match(fn)
            if m:
                days.add("%s-%s-%s" % (m.group(2), m.group(3), m.group(4)))
                continue
            m = MONTH.match(fn)
            if m:
                y, mo = int(m.group(2)), int(m.group(3))
                for dd in range(1, calendar.monthrange(y, mo)[1] + 1):
                    days.add("%04d-%02d-%02d" % (y, mo, dd))
        if days:
            avail[str(code)] = days
    pd.to_pickle(avail, "_min1_avail.pkl")

print("1 分 K 可用的股票數：%d" % len(avail))
span = collections.Counter()
for code, days in avail.items():
    for d in days:
        span[d[:7]] += 1
print("按月可用的 (股票,日) 筆數（前 24 個月）：")
for m in sorted(span)[-24:]:
    print("   %s  %6d" % (m, span[m]), flush=True)

# Now walk the shipped book and collect the trades that stop out on a price limit.
rule = dict(T.BASE); rule["dv_cap"] = T.K_OPEN * 0.10
brake = ((-0.006, 0.50), (-0.012, 0.25))
book = float(T.CAP0); peak = float(T.CAP0)
reasons = collections.Counter()
limit_stops = []
for d in T.days:
    cdd = (book - peak) / peak
    rs = brake[0][1] if cdd < brake[0][0] else (brake[1][1] if cdd < brake[1][0] else 1.0)
    rem = book * 1.0
    for _, r in T.GROUPS[d].sort_values("_rank").iterrows():
        ag = abs(float(r["adj_gap"]))
        cap = 0.08 if r["direction"] == "LONG" else 0.04
        if ag > cap:
            continue
        code = str(r["stock"])
        w = float(r["_weight"]) / (float(r["_rs"]) or 1.0) * rs
        dv1 = float(T.TO1.at[d, code]) if (code in T.TO1.columns and d in T.TO1.index) else float("nan")
        n = T.S.lots_for(rule, w, float(r["entry"]), rem, dv1, capital=book)
        if n <= 0:
            continue
        pr = float(r["entry"])
        ex, slp, tpp, reason, gross = exit_of_legal(
            r["direction"], pr, float(r["day_high"]), float(r["day_low"]),
            float(r["day_close"]), float(r["lu"]), float(r["ld"]),
            float(r["tick"]), float(r["tp"]))
        rem -= n * 1000.0 * pr
        reasons[reason] += 1
        if reason.startswith("停損(觸"):
            limit_stops.append((str(pd.Timestamp(d).date()), code, r["direction"],
                                reason, n * 1000.0 * pr, gross))
    book += sum(x[4] * x[5] for x in [])   # placeholder, PnL not needed here
    book = float(T.CAP0); peak = float(T.CAP0)

print("\n出場原因分布（全部訊號，未含部位/成本）：")
tot = sum(reasons.values())
for k, v in reasons.most_common():
    print("   %-22s %7d  %5.1f%%" % (k, v, v / tot * 100))

have = [x for x in limit_stops if x[1] in avail and x[0] in avail[x[1]]]
print("\n觸漲跌停停損的交易：%d 筆，其中有 1 分 K 可查：%d 筆（%.1f%%）"
      % (len(limit_stops), len(have), len(have) / max(1, len(limit_stops)) * 100))
per_year = collections.Counter(x[0][:4] for x in limit_stops)
per_year_have = collections.Counter(x[0][:4] for x in have)
print("逐年（可查/總數）：")
for y in sorted(per_year):
    print("   %s  %5d / %5d" % (y, per_year_have[y], per_year[y]), flush=True)
pd.to_pickle(have, "_min1_limit_stops.pkl")
pd.to_pickle(limit_stops, "_min1_all_stops.pkl")
print("全部觸板停損已存：", len(limit_stops))
