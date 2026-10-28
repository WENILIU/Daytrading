# -*- coding: utf-8 -*-
"""Is the missing message pump why no OrderLib report event ever arrives?

Every [Reply] / [Account detected] line in the logs sits inside a login burst
(one cluster per process start), so their presence proves nothing about delivery
later in the session - OnAccount is simply an event the server sends at login.
What IS unexplained: GetRealBalanceReport returns SK_SUCCESS six times on
2026-10-28 (including 13:37 and 13:56, after the close) and [BALANCE] never
appears. Two hypotheses fit, and only an experiment separates them:
  H1 no message pump - the events are queued and never dispatched.
  H2 this API/account never sends those events.

Controlled order matters, so: no-pump wait, then pump, then no-pump again.
If only the pump phase delivers, H1 is proven and live would never see its own
smart orders without a pump. If the last no-pump phase delivers too, it was
latency, not the pump. No orders are sent; report queries are not session-bound.
"""
import sys, time, warnings, ctypes
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import pythoncom
import gap_fade_auto as G

try:
    apt, lock = pythoncom.CoGetApartmentType()
    names = {0: "MTA", 1: "STA", 2: "MAINSTA", 3: "NONE"}
    print(f"[0] COM apartment: {names.get(apt, apt)} (lockmode {lock})")
except Exception as e:
    print(f"[0] CoGetApartmentType failed: {e}")

cfg = G.Config()
t = G.GapFadePaperTrader(cfg)
t.connect()


def wait_nopump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        time.sleep(0.5)


def wait_pump(seconds):
    end = time.time() + seconds
    n = 0
    while time.time() < end:
        # Dispatch whatever COM queued on this thread's message queue.
        while True:
            try:
                if not pythoncom.PumpWaitingMessages():
                    break
            except Exception:
                break
        n += 1
        time.sleep(0.05)
    return n


def phase(tag, do_request, wait_fn, seconds, counter):
    before = len(counter)
    do_request()
    extra = wait_fn(seconds)
    got = len(counter) - before
    pump = f" (pumped {extra} iterations)" if isinstance(extra, int) else ""
    print(f"  {tag}: {got} new event(s) in {seconds}s{pump}")
    return got


print("\n[A] balance request, then NO pump for 8s")
a = phase("A no-pump", lambda: t.m_pSKOrder.GetRealBalanceReport(t.user_id, t.account),
          wait_nopump, 8, t._balance_reports)

print("\n[B] balance request again, then PUMP for 12s")
b = phase("B pump", lambda: t.m_pSKOrder.GetRealBalanceReport(t.user_id, t.account),
          wait_pump, 12, t._balance_reports)

print("\n[C] smart-strategy report for 2026-10-26 (six orders were accepted that day), PUMP 10s")
c = phase("C pump", lambda: t.request_smart_report(date_str="2026-10-26"),
          wait_pump, 10, t._smart_reports)

print("\n[D] control: balance request, then NO pump for 10s")
d = phase("D no-pump control", lambda: t.m_pSKOrder.GetRealBalanceReport(t.user_id, t.account),
          wait_nopump, 10, t._balance_reports)

print()
print("=" * 62)
bal_total = len(t._balance_reports)
print(f"balance events total: {bal_total} | smart events total: {len(t._smart_reports)}")
if a == 0 and bal_total > 0 and d == 0:
    print("VERDICT: H1 PROVEN - events arrive only while messages are pumped.")
    print("         gap_fade_auto.py has no pump, so live would never see its")
    print("         own smart-order state. A pump must be added to the loop.")
elif bal_total == 0:
    print("VERDICT: H2 - pumping did not produce a balance event either. The")
    print("         report events are not being sent to this sink at all;")
    print("         the fill channel needs a different mechanism.")
else:
    print("VERDICT: inconclusive - the control phase also delivered, so this is")
    print("         latency, not the pump.")
print("=" * 62)
for b in t._balance_reports[:1]:
    print("BALANCE RAW:", b["text"][:600])
for r in t._smart_reports[:3]:
    print("SMART RAW:", r["row"][:400])
t.disconnect()
