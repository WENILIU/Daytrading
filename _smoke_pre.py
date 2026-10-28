"""End-to-end smoke of the pre-open permission read against the real broker.

Post-close, so this proves the wiring and measures the walk cost for the whole stock
list. It is NOT the 09:00 number - at 09:00 the cache is being filled live - but the
walk is over the same cache either way, so the cost is the number that matters.
"""
import sys, io, time, warnings, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import gap_fade_auto as G

t = G.GapFadeAutoTrader(G.Config())
t.connect()
t0 = time.time()
t._read_day_trade_flags_preopen()
el = time.time() - t0
t.disconnect()
f = t.exec_stats.get("day_trade_flags") or {}
c = collections.Counter(f.values())
print(f"\nwall {el:.2f}s | requested {t.exec_stats.get('day_trade_preopen_codes')} "
      f"| resolved {len(f)} | distribution {dict(sorted(c.items()))}")
uni = {l.strip() for l in open("valid_stocks.txt", encoding="utf-8") if l.strip()}
print("universe covered:", len(uni & set(f)), "/", len(uni))
print("0/1/2 inside universe:", {v: len({k for k in f if k in uni and f[k] == v}) for v in (0, 1, 2)})
