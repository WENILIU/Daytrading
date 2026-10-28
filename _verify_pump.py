# -*- coding: utf-8 -*-
"""Does the trader's own connect() now receive the balance event?

_probe_pump.py proved the pump is required. This checks the fix is actually wired
into the code path a session uses: connect() must come back with balance data
and without the "no balance data within 6s" warning. No orders are sent.
"""
import sys, warnings, logging
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

cfg = G.Config()
t = G.GapFadePaperTrader(cfg)
t.connect()
print()
print("=" * 62)
print(f"balance events received by connect(): {len(t._balance_reports)}")
print(f"smart events: {len(t._smart_reports)}")
ok = len(t._balance_reports) > 0
print("VERDICT:", "the fix works - connect() receives the report event"
      if ok else "STILL BLIND - the fix is not on the path connect() uses")
print("=" * 62)
if t._balance_reports:
    print("first row:", t._balance_reports[0]["text"][:200])
t.disconnect()
sys.exit(0 if ok else 1)
