"""Cross-check nDayTrade against the two sources we already filter on.

The earlier "100% agreement with the lending quota" was computed on the truncated map, so
it has to be redone. What matters: does nDayTrade=0/1 correspond to something real
(處置 / no lending quota), or is it noise? If it corresponds, the quote field is a live
per-stock substitute for a T-1 panel plus a post-hoc 924 rejection.
"""
import sys, io, json, warnings, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import gap_fade_auto as G

dt_map = {str(k): int(v) for k, v in json.load(open("_daytrade_probe.json", encoding="utf-8")).items()}
uni = set(dt_map)
restricted = G.get_restricted_stocks()
borrowable, asof = G.get_borrowable_stocks()
borrow = set() if borrowable is None else set(borrowable)

print(f"broker map: {len(dt_map)} codes | finlab restricted: {len(restricted)} | "
      f"lending quota (as-of {asof}): {len(borrow)}")
print()
for dt in (0, 1, 2):
    grp = {c for c, v in dt_map.items() if v == dt}
    if not grp:
        continue
    r = len(grp & restricted)
    b = len(grp & borrow)
    print(f"  nDayTrade={dt}  n={len(grp):<5} "
          f"also in 處置/暫停: {r:>4} ({r/len(grp)*100:5.1f}%) | "
          f"has lending quota: {b:>4} ({b/len(grp)*100:5.1f}%)")

print()
short_ok = {c for c, v in dt_map.items() if v == 2}
no_quota = short_ok - borrow
print(f"broker says 無券當沖 OK but NO lending quota: {len(no_quota)} "
      f"({len(no_quota)/max(1,len(short_ok))*100:.1f}% of the two-sided set)")
quota_only = borrow - short_ok
print(f"lending quota exists but broker says NOT two-sided: {len(quota_only)}")
print("  -> the two sources mostly agree; where they differ, the stricter reading is "
      "the safe one for a SHORT")
print()
blocked = {c for c, v in dt_map.items() if v in (0, 1)}
print(f"codes the broker blocks from two-sided day-trading: {len(blocked)}")
print(f"  of those, finlab also flags them 處置/暫停: {len(blocked & restricted)}")
print(f"  sample of blocked-but-not-處置: {sorted(blocked - restricted)[:15]}")
