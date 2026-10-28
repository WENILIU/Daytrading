"""Real-broker smoke for _read_day_trade_flags, and how long the cache needs to warm.

The offline test uses a fake quote_lib, so it cannot prove the COM call path works or
that the cache is warm by the time a 09:00 scan finishes. Tonight one enumeration pass
returned 1,928 codes and the next returned none, so the warm-up behaviour is measured
rather than assumed - if the answer arrives only after N seconds, tomorrow's report needs
to read it after that much delay or it will honestly say NOT READ.
"""
import sys, io, time, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import gap_fade_auto as G

codes = [l.strip() for l in open("valid_stocks.txt", encoding="utf-8") if l.strip()][:40]
t = G.GapFadeAutoTrader(G.Config())
t.connect()
for wait in (0.0, 1.0, 2.0, 3.0, 5.0):
    if wait:
        time.sleep(wait)
    t0 = time.time()
    got = t._read_day_trade_flags(codes)
    dt = time.time() - t0
    dist = {}
    for v in got.values():
        dist[v] = dist.get(v, 0) + 1
    print(f"  +{wait:>4.1f}s after connect: {len(got):>3}/{len(codes)} codes "
          f"in {dt:.2f}s  distribution={dict(sorted(dist.items()))}")
t.disconnect()
print("\n(this reads the last session's cache; the values are real but from today's "
      "close, not from tomorrow's open)")
