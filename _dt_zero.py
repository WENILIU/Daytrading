"""Why are 208 codes nDayTrade=0 when nothing else flags them? Stale cache or real block?

nDayTrade=1 matches finlab 處置 on 13/13 - the field means what the manual says. But 208
codes are 0 without being 處置 and without a lending quota, and if I cannot explain them I
should not silently drop 11 pct of the universe on them. The candidate explanation is
staleness: a code whose cached quote is not from today's session would carry an old flag.
Compare nTradingDay / nOpen per bucket.
"""
import sys, io, time, warnings, collections, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import gap_fade_auto as G
import comtypes.gen.SKCOMLib as sk

uni = {l.strip() for l in open("valid_stocks.txt", encoding="utf-8") if l.strip()}
t = G.GapFadeAutoTrader(G.Config())
t.connect()
time.sleep(3)
rec = {}
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
        if s in uni and s not in rec:
            rec[s] = (int(p.nDayTrade), int(p.nTradingDay), float(p.nOpen), float(p.nRef))
        idx += 1
t.disconnect()

by_bucket = collections.defaultdict(lambda: collections.Counter())
for s, (dt, tday, opn, ref) in rec.items():
    by_bucket[dt]["n"] += 1
    by_bucket[dt]["stale_day"] += (tday != 20261028)
    by_bucket[dt]["no_open"] += (opn <= 0)
    by_bucket[dt]["no_ref"] += (ref <= 0)
    by_bucket[dt][f"tday_{tday}"] += 1

print(f"codes read: {len(rec)}")
for dt in sorted(by_bucket):
    c = by_bucket[dt]
    print(f"\n  nDayTrade={dt}  n={c['n']}")
    print(f"    tradingDay != 20261028: {c['stale_day']} ({c['stale_day']/c['n']*100:.1f}%)")
    print(f"    no cached open price:   {c['no_open']} ({c['no_open']/c['n']*100:.1f}%)")
    print(f"    no cached ref price:    {c['no_ref']} ({c['no_ref']/c['n']*100:.1f}%)")
    top = [(k, v) for k, v in c.items() if k.startswith("tday_")]
    top.sort(key=lambda x: -x[1])
    print(f"    tradingDay values: {top[:4]}")
json.dump({s: v[0] for s, v in rec.items()}, open("_daytrade_probe.json", "w", encoding="utf-8"))
