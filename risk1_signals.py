# -*- coding: utf-8 -*-
"""RISK1 for the population the strategy actually signalled today.

signal_history.json keeps symbol -> dates it signalled, so the day's signal set
survives even when the paper run started late and left no rehearsal file. That
set is the decision-relevant population: not "can the market print an open", but
"can the names THIS strategy picked be seen in time".
"""
import sys, json, time, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from gap_fade_auto import Config, GapFadeSimulator, _to_float

DAY = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y-%m-%d")
cfg = Config()
tr = GapFadeSimulator(cfg)
tr.connect()
codes = tr._load_stock_list()
t0 = time.time()
rows, source = tr._batch_scan(codes)
print(f"scan: {len(rows)} rows via {source} in {time.time()-t0:.2f}s")

hist = json.load(open("trading_logs/signal_history.json", encoding="utf-8"))
sig = {s for s, ds in hist.items() if DAY in ds}
print(f"signals produced on {DAY}: {len(sig)} symbols")

open_dt = tr._parse_time("09:00")
lat = {}
for r in rows:
    if not r.get("c"):
        continue
    ot = _to_float(r.get("ot"))
    if ot > 0:
        lat[str(r["c"])] = ot / 1_000_000.0 - open_dt.timestamp()
print(f"codes with an openTime: {len(lat)}")


def report(name, syms):
    v = sorted(lat[s] for s in syms if s in lat)
    if not v:
        print(f"\n{name}: n=0")
        return
    n = len(v)
    q = lambda p: v[min(n - 1, int(p * n))]
    print(f"\n{name}: n={n} (of {len(syms)} signals, {len(syms)-n} had no openTime)")
    print(f"  p50 {q(0.5):6.2f}s | p90 {q(0.9):7.2f}s | p99 {q(0.99):8.2f}s | max {v[-1]:8.2f}s")
    for cut in (5, 10, 15, 30):
        w = sum(1 for x in v if x <= cut)
        print(f"    visible by 09:00:{cut:>2}  {w:>4}/{n}  {w/n*100:5.1f}%")


report(f"signals produced on {DAY}", sig)
if "2330" in lat:
    print(f"\n  sanity check 2330: {lat['2330']:.2f}s "
          "(live-measured 8.98s on 2026-10-22; the 10-27 offline read was 8.68s)")
tr.disconnect()
