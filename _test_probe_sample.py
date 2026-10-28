# -*- coding: utf-8 -*-
"""The quote-readiness probe must describe the population we trade.

It used valid_stocks.txt[:100]. That file is sorted, so the slice was ETFs plus
oldest-sector names - a gate on it answers "are the ETFs ready". Measured on
2026-10-28 the opening-print latency differs by more than a factor of two
between that group and the strategy signal set, so the gate was not measuring
what the orders depend on.
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(f"  [{'OK  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if not cond else ""))


codes = [l.strip() for l in open("valid_stocks.txt", encoding="utf-8") if l.strip()]
check("the real universe is loaded", len(codes) > 1500, f"{len(codes)} codes")

s = G.spread_sample(codes, 100)
check("still 100 probes, no duplicates", len(s) == 100 and len(set(s)) == 100,
      f"{len(s)} items, {len(set(s))} unique")
check("it is no longer the first 100 lines of the file", s != codes[:100],
      "sampling still returns the head of the list")
check("it reaches the end of the market, not just the low codes",
      codes.index(s[-1]) >= len(codes) - int(len(codes) * 0.05)
      and sum(1 for x in s if x >= "6000") > 20,
      f"last index={codes.index(s[-1])} of {len(codes)}, "
      f"high-code count={sum(1 for x in s if x >= '6000')}")
check("indices are increasing, so the scan order is unchanged",
      [codes.index(x) for x in s] == sorted(codes.index(x) for x in s))

check("a list shorter than the request is returned whole",
      G.spread_sample(["1", "2", "3"], 10) == ["1", "2", "3"])
check("n=0 asks for everything rather than nothing",
      G.spread_sample(["1", "2", "3"], 0) == ["1", "2", "3"])

print()
ok = all(results)
print(f"{sum(results)}/{len(results)} checks passed -> " + ("ALL OK" if ok else "FAILED"))
sys.exit(0 if ok else 1)
