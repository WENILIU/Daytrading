# -*- coding: utf-8 -*-
"""The broker's day-trade permission is reported per signal, never silently enforced.

Measured 2026-10-28 on the real broker cache: nDayTrade is populated for 1,928/1,928
codes in our universe, every row stamped with that day's session, and nDayTrade=1 matches
the finlab 處置 list on 13 of 13 - the field means what the manual says. But 221 codes
are 0 without being 處置 and are unexplained, and one enumeration pass returned 1,928
codes while the next returned none. So the two failure modes these checks pin down are:

  * treating "could not read" as "all allowed" (the cache is not always warm), and
  * quietly dropping signals on a flag we cannot yet explain.
"""
import sys, json, logging, tempfile, warnings
from pathlib import Path
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import gap_fade_auto as G

results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(f"  [{'OK  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if not cond else ""))


def trader():
    t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
    t.config = G.Config()
    t.config.log_dir = tempfile.mkdtemp()
    msgs = []
    lg = logging.getLogger("dt" + str(id(t)))
    lg.handlers = [type("H", (logging.Handler,), {"emit": lambda self, r: msgs.append(
        r.getMessage())})()]
    lg.setLevel(logging.INFO)
    t.log = lg
    t.exec_stats = {"orders": [], "entry_slippage": []}
    t.closed_trades = []
    t._smart_reports = []
    t._msgs = msgs
    return t


class FakeStruct:
    """Stands in for sk.SKSTOCKLONG(); the method only reads two fields off it."""
    def __init__(self):
        self.bstrStockNo = ""
        self.nDayTrade = -1


class FakeQuoteLib:
    def __init__(self, table):
        self.table = table          # {code: nDayTrade}
        self.calls = 0

    def SKQuoteLib_GetStockByIndexLONG(self, market_no, idx, p):
        self.calls += 1
        if idx >= len(self.table):
            return p, 1               # non-zero = end of this market
        code = list(self.table)[idx]
        p.bstrStockNo = code
        p.nDayTrade = self.table[code]
        return p, 0


t = trader()
check("no quote_lib means no answer, not an empty answer treated as allowed",
      t._read_day_trade_flags(["2330"]) == {}, "quote_lib absent")
t.quote_lib = FakeQuoteLib({})
check("no codes requested short-circuits before touching the feed",
      t._read_day_trade_flags([]) == {} and t.quote_lib.calls == 0)

t = trader()
table = {"2330": 2, "2454": 0, "2492": 1}
t.quote_lib = FakeQuoteLib(table)
got = t._read_day_trade_flags(list(table))
check("the flag is read per code, including the values that say NO",
      got == table, str(got))
check("a code the feed does not carry is absent, not defaulted to allowed",
      t._read_day_trade_flags(["2330", "9999"]) == {"2330": 2}, str(got))

# --- warm-up: the cache is not ready the instant connect() returns ----------
class WarmingQuoteLib:
    """Resolves nothing on the first pass, everything on the second."""
    def __init__(self, table):
        self.table = table
        self.passes = 0

    def SKQuoteLib_GetStockByIndexLONG(self, market_no, idx, _p):
        if idx == 0:
            self.passes += 1
        if self.passes < 2:
            return _p, 1                      # cold cache: nothing yet
        if idx >= len(self.table):
            return _p, 1
        code = list(self.table)[idx]
        _p.bstrStockNo = code
        _p.nDayTrade = self.table[code]
        return _p, 0


t = trader()
warm = WarmingQuoteLib({"2330": 2, "2454": 0})
t.quote_lib = warm
got2 = t._read_day_trade_flags(["2330", "2454"], budget_sec=5.0, poll=0.05)
check("a cold cache is retried instead of reported as a partial result",
      got2 == {"2330": 2, "2454": 0} and warm.passes >= 2,
      f"passes={warm.passes} got={got2}")


class ColdForeverQuoteLib:
    def __init__(self):
        self.passes = 0

    def SKQuoteLib_GetStockByIndexLONG(self, market_no, idx, _p):
        if idx == 0:
            self.passes += 1
        return _p, 1


t = trader()
t.quote_lib = ColdForeverQuoteLib()
t0 = __import__("time").time()
got3 = t._read_day_trade_flags(["2330"], budget_sec=1.0, poll=0.05)
elapsed = __import__("time").time() - t0
check("a cache that never warms returns within the budget, not forever",
      got3 == {} and elapsed < 3.0, f"elapsed={elapsed:.2f}s")


# --- the report path --------------------------------------------------------
sig_short_ok = G.Signal(symbol="2330", name="A", direction=G.Direction.SHORT,
                        open_price=100.0, prev_close=95.0, raw_gap=.05, adj_gap=.05)
sig_short_ok.day_trade = 2
sig_short_no = G.Signal(symbol="2454", name="B", direction=G.Direction.SHORT,
                        open_price=50.0, prev_close=47.0, raw_gap=.06, adj_gap=.06)
sig_short_no.day_trade = 0
sig_long = G.Signal(symbol="2492", name="C", direction=G.Direction.LONG,
                    open_price=40.0, prev_close=43.0, raw_gap=-.07, adj_gap=-.07)
sig_long.day_trade = 1

t = trader()
t.signals = [sig_short_ok, sig_short_no, sig_long]
t.exec_stats["day_trade_flags"] = {"2330": 2, "2454": 0, "2492": 1}
t.exec_stats["day_trade_coverage"] = [3, 3]
t.exec_stats["day_trade_wait_s"] = 0.4
t._paper_report()
f = next(p for p in Path(t.config.log_dir).iterdir() if p.suffix == ".json")
d = json.loads(f.read_text(encoding="utf-8"))
check("the report counts each permission level instead of a single yes/no",
      d["day_trade_summary"]["counts"] == {"2": 1, "1": 1, "0": 1, "-1": 0},
      str(d["day_trade_summary"]["counts"]))
check("only the SHORT on a blocked code is counted, not the SHORT on an allowed one",
      any("SHORT signals the broker would not allow: 1" in m for m in t._msgs),
      str([m for m in t._msgs if "SHORT" in m][:2]))
check("a LONG on nDayTrade=1 is NOT blocked - 1 means 先買後賣, which is what a LONG needs",
      d["day_trade_summary"]["counts"]["1"] == 1
      and not any("LONG signals" in m for m in t._msgs), str(d["day_trade_summary"]))
check("it states this is the product's permission, not the account's 924",
      any("924" in m and "PRODUCT" in m for m in t._msgs), str(t._msgs[-3:]))
check("and it says the flag is NOT enforced, so nobody reads it as a filter",
      any("NOT filtered" in m for m in t._msgs) and d["day_trade_summary"]["enforced"] is False,
      str(d["day_trade_summary"]))

check("full coverage is stated as full coverage",
      any("resolved 3/3 signal codes" in m for m in t._msgs),
      str([m for m in t._msgs if "resolved" in m]))
check("the JSON carries the coverage so the number is not read unattributed",
      d["day_trade_coverage"] == [3, 3], str(d.get("day_trade_coverage")))

t2 = trader()
t2.signals = [sig_short_ok]
t2._paper_report()

t3b = trader()
t3b.signals = [sig_short_ok, sig_short_no]
t3b.exec_stats["day_trade_flags"] = {"2330": 2}
t3b.exec_stats["day_trade_coverage"] = [1, 2]
t3b._paper_report()
check("a PARTIAL cache is called out as partial and the unknown bucket labelled unresolved",
      any("PARTIAL" in m and "unresolved" in m for m in t3b._msgs),
      str([m for m in t3b._msgs if "PARTIAL" in m]))

t4 = trader()
t4.signals = [sig_short_ok]
t4._paper_report()
check("an unread flag is reported as NOT READ, never as allowed",
      any("day-trade permission: NOT READ" in m and "not the same as" in m
          for m in t2._msgs), str([m for m in t2._msgs if "day-trade" in m]))

t3 = trader()
t3._paper_report()
check("a stub with no signals at all still reports, instead of crashing",
      any("day-trade permission: NOT READ" in m for m in t3._msgs), str(t3._msgs[-2:]))

print()
ok = all(results)
print(f"{sum(results)}/{len(results)} checks passed -> " + ("ALL OK" if ok else "FAILED"))
sys.exit(0 if ok else 1)
