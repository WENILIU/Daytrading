# -*- coding: utf-8 -*-
"""Does bstrDate work when given the documented YYYYMMDD format?

At 14:29 a query for 2026-10-26 returned today's rows, which was written up as
"the date parameter is ignored". The manual says the format is YYYYMMDD
(ex:20201001) and the sample UI placeholder is "YYYYMMDD" - the value sent was
"2026-10-26". If the correct format returns 20261026 rows, the claim was mine,
not the broker's, and 2026-10-26 matters: that session had six ACCEPTED smart
orders, so its rows carry a different status code than today's 32 and are the
differential sample needed to decode the status field.
"""
import sys, time, warnings, collections
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

cfg = G.Config()
t = G.GapFadePaperTrader(cfg)
t.connect()

for d in ("20261026", "2026-10-26", ""):
    before = len(t._smart_reports)
    n = t.request_smart_report(date_str=d)
    G.pump_messages(12.0)
    rows = [r["row"] for r in t._smart_reports[before:] if not r["row"].startswith("##")]
    days = collections.Counter(r.split(",")[2] if r.count(",") > 2 else "?" for r in rows)
    stat = collections.Counter(r.split(",")[18] if r.count(",") > 18 else "?" for r in rows)
    print(f"  date={d!r:<14} rows={len(rows):>3}  trading-day field={dict(days)}  field19={dict(stat)}")

t.disconnect()
