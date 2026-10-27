"""RISK1, measured on the population the strategy actually trades.

The full-market opening-print distribution is not decision-relevant: the strategy
only ever trades names above a T-1 turnover floor, and those are the liquid ones.
Half of the market having no print until 34 minutes after the open says nothing
about whether THIS strategy can get an opening fill.

So measure it three ways from the same field:
  all 1928 codes | the strategy's eligible pool | the signals it actually produced
  today | the tickets it actually funded.

`ot` is what Fugle reports as the time of the day's first trade. For a stock with
an opening-auction print that IS the 09:00:00 print; for a stock with no auction
trade it is the first trade later in the session. Cross-checked against 2330,
which was measured live at 09:00:08.98 on 2026-10-22.
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, ".")
from gap_fade_auto import Config, GapFadeSimulator, _to_float

cfg = Config()
tr = GapFadeSimulator(cfg)
tr.connect()

rehearsal = Path("trading_logs/rehearsal_20261027.json")
if not rehearsal.exists():
    print("run paper_rehearsal.py first")
    sys.exit(1)
R = json.loads(rehearsal.read_text(encoding="utf-8"))
sig_by_sym = {s["symbol"]: s for s in R["signals"]}
funded = {o["symbol"] for o in R["orders"]}

codes = tr._load_stock_list()
rows = []
t0 = time.time()
rows, source = tr._batch_scan(codes)
print(f"scan: {len(rows)} rows via {source} in {time.time()-t0:.2f}s")

open_dt = tr._parse_time("09:00")
recs = []
for r in rows:
    if not r.get("c"):
        continue
    ot = _to_float(r.get("ot"))
    if ot <= 0:
        continue
    recs.append({
        "sym": str(r["c"]),
        "lat": ot / 1_000_000.0 - open_dt.timestamp(),
        "turnover": _to_float(r.get("tv")) or _to_float(r.get("pv")) * _to_float(r.get("o")),
        "ex": r.get("x") or "?",
    })
print(f"rows with an openTime: {len(recs)}")

# T-1 turnover for the eligible-pool cut comes from the signal records where
# available; the live feed only carries TODAY's turnover, so use the panel value
# the scan itself used (prev_turnover) for the names the strategy considered.
floor = cfg.min_turnover_factor * cfg.capital


def report(name, group):
    if not group:
        print(f"\n{name}: n=0")
        return
    v = sorted(g["lat"] for g in group)
    n = len(v)
    q = lambda p: v[min(n - 1, int(p * n))]
    print(f"\n{name}: n={n}")
    print(f"  p50 {q(0.5):6.2f}s | p90 {q(0.9):7.2f}s | p99 {q(0.99):8.2f}s | max {v[-1]:8.2f}s")
    for cut in (1, 2, 5, 10, 30):
        within = sum(1 for x in v if x <= cut)
        print(f"    visible by 09:00:{cut:>2}  {within:>5}/{n}  {within/n*100:5.1f}%")


report("A) every code the feed answers for", recs)
by_ex = {}
for g in recs:
    by_ex.setdefault(g["ex"], []).append(g)
for ex, grp in sorted(by_ex.items()):
    report(f"B) by exchange: {ex}", grp)

elig = [g for g in recs if sig_by_sym.get(g["sym"], {}).get("prev_turnover", 0) >= floor]
report(f"C) strategy-eligible pool (T-1 turnover >= {floor/1e4:.0f}wan)", elig)
report("D) signals produced today", [g for g in recs if g["sym"] in sig_by_sym])
fund = [g for g in recs if g["sym"] in funded]
report("E) tickets actually funded today", fund)
print()
for g in sorted(fund, key=lambda x: x["lat"]):
    print(f"    {g['sym']:<7} open print {g['lat']:6.2f}s after 09:00:00")

chk = [g for g in recs if g["sym"] == "2330"]
if chk:
    print(f"\n  sanity check 2330 today: {chk[0]['lat']:.2f}s "
          f"(the live-measured 2026-10-22 value was 8.98s)")
