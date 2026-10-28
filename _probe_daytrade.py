"""Is SKSTOCKLONG.nDayTrade populated, and does it add anything we do not already have?

The manual documents, on the per-stock quote struct:
  nDayTrade  [限證券整股商品]可否當沖  0:一般  1:可先買後賣現股當沖  2:也可先賣後買
If that arrives with the quote, the 09:00 scan could know per candidate whether the
direction is day-tradeable at all, instead of learning it from a 924 rejection after the
order is sent. Two things must hold before it is worth using: it must actually be
populated (not a constant), and it must say something the current 處置 / lending-quota
filters do not already say. Both are checked here.

Run after the close: the quote cache still holds the last session, which answers both.
"""
import sys, io, json, time, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import gap_fade_auto as G
import comtypes.gen.SKCOMLib as sk

# the real constructor, not __new__ - connect() wires COM callbacks that need the
# instance state the constructor builds
t = G.GapFadeAutoTrader(G.Config())
t.connect()
time.sleep(3)

rows = {}
for market_no in (0, 1):
    idx = 0
    while idx < 6000:
        p = sk.SKSTOCKLONG()
        try:
            p, code = t.quote_lib.SKQuoteLib_GetStockByIndexLONG(market_no, idx, p)
        except Exception:
            break
        if code != 0:
            break
        s = str(p.bstrStockNo or "")
        if s:
            rows[s] = int(p.nDayTrade)
        idx += 1

print(f"stocks read from the broker quote cache: {len(rows)}")
dist = {}
for s, dt in rows.items():
    dist[dt] = dist.get(dt, 0) + 1
print("nDayTrade distribution:", dict(sorted(dist.items())))
print("  0=不可當沖 1=可先買後賣(資沖) 2=也可先賣後買(無券當沖)")

if len(set(rows.values())) == 1:
    print("\n  VERDICT: constant value -> the field carries no per-stock information here.")
else:
    print("\n  field varies by stock -> worth cross-checking against what we filter on")
    restricted = G.get_restricted_stocks()
    borrowable, asof = G.get_borrowable_stocks()
    print(f"  our filters: restricted(處置/暫停) {len(restricted)} codes | "
          f"borrowable {0 if borrowable is None else len(borrowable)} (as-of {asof})")
    both = {s for s, d in rows.items() if d == 2}
    one = {s for s, d in rows.items() if d == 1}
    none = {s for s, d in rows.items() if d == 0}
    for label, mine, theirs in (("處置/暫停", restricted, none | one),
                                ("not borrowable", (set() if borrowable is None else
                                                    set(rows) - borrowable), none)):
        if mine:
            inter = len(mine & theirs)
            print(f"    {label}: {len(mine)} of our codes; broker also excludes {inter} "
                  f"({inter/len(mine)*100:.1f}%)")
    if borrowable is not None:
        short_ok = {s for s in rows if rows[s] == 2}
        agree = len(short_ok & borrowable)
        print(f"    SHORT-able by broker (nDayTrade=2): {len(short_ok)} | "
              f"of those, lending quota present: {agree} "
              f"({agree/max(1,len(short_ok))*100:.1f}%)")
json.dump(rows, open("_daytrade_probe.json", "w", encoding="utf-8"))
print("\nwritten _daytrade_probe.json")
t.disconnect()
