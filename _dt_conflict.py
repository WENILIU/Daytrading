"""Does the same code appear under several markets with different nDayTrade?

If a code is reachable through more than one market index and the values differ, then
"first one seen wins" is an arbitrary choice and the 221 zeros could be an artifact of
enumeration order rather than a real block. Collect every (market, value) pair per code.
"""
import sys, io, time, warnings, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import gap_fade_auto as G
import comtypes.gen.SKCOMLib as sk

uni = {l.strip() for l in open("valid_stocks.txt", encoding="utf-8") if l.strip()}
t = G.GapFadeAutoTrader(G.Config())
t.connect()
time.sleep(3)
seen = collections.defaultdict(list)
for market_no in (0, 1, 2, 3, 4, 5):
    idx = 0
    while idx < 200000:
        p = sk.SKSTOCKLONG()
        try:
            p, code = t.quote_lib.SKQuoteLib_GetStockByIndexLONG(market_no, idx, p)
        except Exception:
            break
        if code != 0:
            break
        s = str(p.bstrStockNo or "")
        if s in uni:
            seen[s].append((market_no, int(p.nDayTrade), idx))
        idx += 1
t.disconnect()

multi = {s: v for s, v in seen.items() if len(v) > 1}
conflict = {s: v for s, v in multi.items() if len({x[1] for x in v}) > 1}
print(f"codes seen: {len(seen)} | appearing under >1 market: {len(multi)} | "
      f"with CONFLICTING nDayTrade: {len(conflict)}")
for s, v in list(conflict.items())[:8]:
    print(f"  {s}: {v}")

mk = collections.Counter()
for s, v in seen.items():
    for m, dt, _i in v:
        mk[(m, dt)] += 1
print("\n(value counts by market):", dict(sorted(mk.items())))

final = {s: sorted(v, key=lambda x: (x[0], x[2]))[0][1] for s, v in seen.items()}
print("\ndistribution taking the FIRST entry per code:",
      dict(sorted(collections.Counter(final.values()).items())))
best = {}
for s, v in seen.items():
    best[s] = max(x[1] for x in v)
print("distribution taking the MOST PERMISSIVE entry:",
      dict(sorted(collections.Counter(best.values()).items())))
import json
json.dump(final, open("_daytrade_probe.json", "w", encoding="utf-8"))
json.dump(best, open("_daytrade_probe_permissive.json", "w", encoding="utf-8"))
