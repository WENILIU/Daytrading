"""nDayTrade for exactly the codes our strategy can trade - no shape guessing.

Two enumeration errors in a row: a 6000 index cap, then a len==5 filter that dropped the
4-digit majority of TWSE codes. The universe file already defines what is a stock, so
intersect with it directly and report only that.
"""
import sys, io, json, time, warnings, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import gap_fade_auto as G
import comtypes.gen.SKCOMLib as sk
import pandas as pd

uni = {l.strip() for l in open("valid_stocks.txt", encoding="utf-8") if l.strip()}
print(f"universe from valid_stocks.txt: {len(uni)} | "
      f"lengths {dict(sorted(collections.Counter(len(c) for c in uni).items()))}")

t = G.GapFadeAutoTrader(G.Config())
t.connect()
time.sleep(3)
dt_map = {}
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
            dt_map.setdefault(s, int(p.nDayTrade))
        idx += 1
t.disconnect()

print(f"universe codes found in the broker cache: {len(dt_map)}/{len(uni)} "
      f"({len(dt_map)/len(uni)*100:.1f}%)")
d = collections.Counter(dt_map.values())
print("nDayTrade over our universe:", dict(sorted(d.items())))
print("  0=不可當沖 1=只能先買後賣 2=也可先賣後買(無券當沖)")

df = pd.read_pickle("signals_v13.pkl")
df = df[df["pred"].notna() & (df["pred_q"] >= 0.20)].copy()
df["stock"] = df["stock"].astype(str)
print(f"\nmodel signals: {len(df)}")
for direc in ("SHORT", "LONG"):
    sub = df[df["direction"] == direc]
    ok = (lambda s: dt_map.get(s, -1) == 2) if direc == "SHORT" else (lambda s: dt_map.get(s, -1) >= 1)
    known = sum(1 for s in sub["stock"] if s in dt_map)
    rows_ok = sum(1 for s in sub["stock"] if ok(s))
    print(f"  {direc}: rows {len(sub)} | code known to us {known} | "
          f"day-tradeable rows {rows_ok} ({rows_ok/len(sub)*100:.1f}%)")
    unk = sum(1 for s in sub["stock"] if s not in dt_map)
    if unk:
        print(f"      (not in the cache at all: {unk} rows - unknown, NOT counted as blocked)")
json.dump(dt_map, open("_daytrade_probe.json", "w", encoding="utf-8"))
print("\nwritten _daytrade_probe.json")
