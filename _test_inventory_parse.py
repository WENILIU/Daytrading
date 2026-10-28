# -*- coding: utf-8 -*-
"""The 可資沖 / 可券沖 reading must come from the manual's 19-field layout.

The rows below are the real ones received on 2026-10-28. The SDK's own
SKDLLPython.py struct has 18 fields and omits the "此欄請忽略" column, so a
parser written from that struct reads 維持率 / LOGIN_ID as inventory from index
15 on. And v2.13.42~v2.13.54 returned 可資沖 and 可券沖 swapped, so the two
columns must not be collapsed into one "can day-trade" flag.
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

# real rows, captured 2026-10-28 14:31 through OnRealBalanceReport
ROW = ("2383,T,0,0,0,0,11,0,0,0,0,11,0,0,11,0,,D121280815,913R0438724")
ROW2 = ("6239,T,0,0,0,0,314,0,0,0,0,314,0,0,314,0,,D121280815,913R0438724")
END = "##,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,"

results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(f"  [{'OK  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if not cond else ""))


rows = G.parse_realtime_inventory(ROW + "#" + ROW2 + "#" + END)
check("two stock rows parsed, the ## terminator is not one", len(rows) == 2, str(rows))
r = rows[0] if rows else {}
check("symbol and inventory type", r.get("symbol") == "2383" and r.get("inventory_type") == "T", str(r))
check("yesterday inventory reads 11, not the 維持率 column", r.get("yesterday_inventory") == 11, str(r))
check("sellable (可賣出) reads 11", r.get("sellable") == 11, str(r))
check("可資沖 and 可券沖 are read as separate fields, both 0 here",
      r.get("daytrade_buyable") == 0 and r.get("daytrade_sellable") == 0, str(r))
check("realtime inventory reads 11 (index 14), not the ignored column",
      r.get("inventory") == 11, str(r))
check("second row keeps its own numbers", (rows[1].get("symbol"), rows[1].get("inventory")) == ("6239", 314)
      if len(rows) > 1 else False, str(rows[1:] ))

# a qualified account: 可券沖 > 0 must show up as sellable, and must not be read as buyable
QUAL = "2383,T,0,0,0,0,0,0,0,0,0,0,3000,2000,0,0,,D121280815,913R0438724"
q = G.summarize_daytrade_quota(G.parse_realtime_inventory(QUAL))
check("a row with 可資沖=3000 / 可券沖=2000 is reported as both, not merged",
      q["known"] and q["buyable"] == 1 and q["sellable"] == 1, str(q))

# the distinction that matters: no rows is unknown, not zero
empty = G.summarize_daytrade_quota([])
check("no rows is 'cannot tell', not 'no quota'", empty["known"] is False, str(empty))
zero = G.summarize_daytrade_quota(G.parse_realtime_inventory(ROW))
check("rows that all say 0 is a real finding", zero["known"] and zero["buyable"] == 0 and zero["sellable"] == 0,
      str(zero))

print()
ok = all(results)
print(f"{sum(results)}/{len(results)} checks passed -> " + ("ALL OK" if ok else "FAILED"))
sys.exit(0 if ok else 1)
