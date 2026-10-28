# -*- coding: utf-8 -*-
"""End-to-end: can a live session actually read its own order state?

No orders are sent here. The six probes from this morning are still queryable
because the channel answers for today only, so this is the closest thing to a
real-session proof that can be made outside one.
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

t = G.GapFadePaperTrader(G.Config())
t.connect()
t.request_smart_report()
G.pump_messages(12.0)
s = t._log_smart_status()
print()
print("=" * 66)
print(f"rows received: {len(t._smart_reports)} | decoded orders: {len(s['orders'])} "
      f"| undecoded: {len(s['unparsed'])}")
ok = bool(s["orders"]) and not s["unparsed"]
print("VERDICT:", "the status channel is readable end to end - a live session "
      "can see its own orders' state" if ok else
      "NOT proven - rows were received but could not all be decoded")
print("=" * 66)
t.disconnect()
sys.exit(0 if ok else 1)
