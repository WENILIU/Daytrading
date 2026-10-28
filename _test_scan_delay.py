# -*- coding: utf-8 -*-
"""Entry timing is a parameter, and a run must say which value it used.

Measured 2026-10-28: scanning at :10 sees 57 pct of the day's signals, at :30
96 pct; waiting 60s costs +0.132 pct/trade. Which side wins is not settled, so
the only honest instrument is one that takes the delay as an input and records
it - otherwise a slippage number from a late scan gets read as the strategy's.
"""
import sys, time, json, logging, tempfile, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(f"  [{'OK  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if not cond else ""))


def trader(delay, cls=None):
    cls = cls or G.GapFadeAutoTrader
    t = cls.__new__(cls)
    t.config = G.Config()
    t.config.scan_delay_sec = delay
    t.config.log_dir = tempfile.mkdtemp()
    lg = logging.getLogger("d" + str(id(t)))
    msgs = []
    lg.handlers = [type("H", (logging.Handler,), {"emit": lambda self, r: msgs.append(
        r.getMessage())})()]
    lg.setLevel(logging.INFO)
    t.log = lg
    t.exec_stats = {"orders": [], "entry_slippage": []}
    t._msgs = msgs
    return t


t = trader(0.0)
t.exec_stats["t_open"] = time.time() - 5
t._hold_until_open_plus_delay()
check("delay 0 keeps the old behaviour and still records the value",
      t.exec_stats["scan_delay_sec"] == 0.0 and t.exec_stats["scan_delay_applied"] is False,
      str(t.exec_stats))

t = trader(30.0)
t.exec_stats["t_open"] = time.time() - 100
t._hold_until_open_plus_delay()
check("a delay that has already passed is reported as NOT applied, not silently skipped",
      t.exec_stats["scan_delay_applied"] is False, str(t.exec_stats))
check("and it says the slippage belongs to the late start, not to +30s",
      any("NOT applied" in m and "late start" in m for m in t._msgs), str(t._msgs[-2:]))

t = trader(2.0)
t0 = time.time()
t.exec_stats["t_open"] = t0 - 1.0
t._hold_until_open_plus_delay()
elapsed = time.time() - t0
check("a delay still in reach is actually held until open+delay",
      t.exec_stats["scan_delay_applied"] is True and 0.9 <= elapsed <= 1.6,
      f"slept {elapsed:.2f}s, expected ~1.0s to reach open+2s")

# the value has to survive into the report, or the number is unattributable
t = trader(30.0, cls=G.GapFadePaperTrader)
t.closed_trades = []
t._smart_reports = []
t.exec_stats["t_open"] = time.time() - 100
t._hold_until_open_plus_delay()
t._paper_report()
out = Path(t.config.log_dir)
f = next(p for p in out.iterdir() if p.suffix == ".json")
d = json.loads(f.read_text(encoding="utf-8"))
check("the feasibility report carries the entry timing this run used",
      d.get("scan_delay_sec") == 30.0 and d.get("scan_delay_applied") is False,
      str({k: d.get(k) for k in ("scan_delay_sec", "scan_delay_applied")}))

print()
ok = all(results)
print(f"{sum(results)}/{len(results)} checks passed -> " + ("ALL OK" if ok else "FAILED"))
sys.exit(0 if ok else 1)
