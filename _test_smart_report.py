# -*- coding: utf-8 -*-
"""The smart-order row decoder must only report what it can validate.

The two rows are the real ones received on 2026-10-28 (recovered from the day's
log). Every asserted value below is one we know we sent, which is what makes the
tail layout - two fields earlier than the manual numbers them - evidence rather
than a guess. The rest of the cases are what happens when the shape changes:
an undocumented status, a filled order, a truncated row.
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

ROW_6108 = ("27478651,TS,20261028,TSE,913R,0438724,0000000,11,6108,S,8,0,7,2,0,"
            "2026-10-28 13:37:42.000,34.1,1,32,,2026-10-28 13:37:42,"
            "[27478651][6108]msg,,,,0,0,,20,1,0,33.45,1,0,0,1,0,25.7,1,0,0,1,"
            "2026-10-29 13:20:00.000,1,0,0,0,0001-01-01 08:00:00.000,,[in], [out],")
ROW_6278 = ("27478650,TS,20261028,TSE,913R,0438724,0000000,11,6278,S,8,0,7,2,0,"
            "2026-10-28 13:37:42.000,306,1,32,,2026-10-28 13:37:42,"
            "[27478650][6278]msg,,,,0,0,,20,1,0,301.5,1,0,0,1,0,232,1,0,0,1,"
            "2026-10-29 13:20:00.000,1,0,0,0,0001-01-01 08:00:00.000,,[in], [out],")

results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(f"  [{'OK  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if not cond else ""))


a = G.parse_smart_strategy_report(ROW_6108)
check("a real row parses cleanly", a["parsed"], str(a["problems"]))
check("symbol / side / order id come from the documented positions",
      (a.get("symbol"), a.get("side"), a.get("order_id")) == ("6108", "S", "27478651"), str(a))
check("order kind 8 is named 無券普賣 - the attribute 924 refuses",
      a.get("order_kind_text") == "無券普賣", str(a.get("order_kind_text")))
check("price type 7 is named 使用者輸入價", a.get("price_type_text") == "使用者輸入價",
      str(a.get("price_type_text")))
check("the probe price we passed is read as the limit price", a.get("limit_price") == 34.1,
      str(a.get("limit_price")))
check("paper_probe_zhang=1 is read as the quantity", a.get("qty_zhang") == 1, str(a.get("qty_zhang")))
check("status 32 decodes to 中台收單成功", a.get("status_code") == 32 and a.get("status_text") == "中台收單成功",
      str(a.get("status_code")))
check("empty 成交數量 is 0 filled, and this order is not filled",
      a.get("filled_qty") == 0 and a.get("filled") is False, str(a.get("filled_qty")))

b = G.parse_smart_strategy_report(ROW_6278)
check("a second real row parses and keeps its own numbers",
      b["parsed"] and (b.get("symbol"), b.get("limit_price")) == ("6278", 306.0), str(b.get("problems")))

# a fill must be caught from either signal
filled_status = ROW_6108.replace(",32,,", ",41,,")
f1 = G.parse_smart_strategy_report(filled_status)
check("status 41 全部成交 is read as filled", f1["parsed"] and f1["filled"] is True, str(f1.get("status_code")))
filled_qty = ROW_6108.replace(",32,,", ",38,1000,")
f2 = G.parse_smart_strategy_report(filled_qty)
check("成交數量 > 0 is read as filled even when the status is 觸發下單",
      f2["parsed"] and f2["filled"] is True, str(f2.get("filled_qty")))

# when the shape changes, refuse instead of inventing
odd_row = ROW_6108.replace(",32,,", ",99,,")
odd = G.parse_smart_strategy_report(odd_row)
check("an undocumented status code makes the row unparsed, with a reason",
      odd["parsed"] is False and any("not a documented code" in x for x in odd["problems"]),
      str(odd["problems"]))
check("an unparsed row still keeps the raw text so it can be read by hand",
      odd.get("raw") == odd_row, "raw missing")
short = G.parse_smart_strategy_report("27478651,TS,20261028,TSE,913R,0438724")
check("a truncated row is refused, not half-parsed",
      short["parsed"] is False and "symbol" not in short, str(short))
for marker, label in [("##", "bare ## marker"), ("##,,,,,,,,", "## padded with commas"),
                      ("", "empty row")]:
    m = G.parse_smart_strategy_report(marker)
    check(f"the {label} is refused but marked ignorable, so it cannot raise a false alarm",
          m["parsed"] is False and m.get("ignorable") is True, str(m))
check("a truncated real row is NOT ignorable - unknown rows stay loud",
      short["parsed"] is False and short.get("ignorable") is False, str(short))


# --- the summary buckets: what the feasibility report reads ---
# The real stream repeats every order several times (the 2026-10-28 rows came in
# four report pushes), so newest-state-per-order and no double counting is not a
# detail, it is the difference between "6 orders" and "24 orders".
def with_status(row, oid, status, filled=""):
    r = row.replace(row.split(",")[0] + ",", oid + ",", 1)
    return r.replace(",32,,", f",{status},{filled},")


t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
t._smart_reports = [{"row": x} for x in [ROW_6108, ROW_6108, "##"]]
sm = t._smart_status_summary()
check("repeated rows for one order collapse to one order, and ## is not a bad row",
      len(sm["orders"]) == 1 and not sm["unparsed"],
      f'{len(sm["orders"])} orders, {len(sm["unparsed"])} unparsed')
check("a session where nothing fired is reported as nothing fired",
      sm["triggered"] == [] and sm["filled"] == [] and sm["rejected"] == []
      and sm["by_status"] == {32: 1}, str(sm))

t._smart_reports = [{"row": x} for x in [
    ROW_6108,
    with_status(ROW_6278, "27478650", 38),
    with_status(ROW_6108, "27478652", 41, "1000"),
    with_status(ROW_6108, "27478653", 33),
]]
sm2 = t._smart_status_summary()
check("status 38 is counted as a trigger - that is the stop-loss actually firing",
      sm2["triggered"] == ["27478650"], str(sm2["triggered"]))
check("a real fill is counted as broker-confirmed",
      sm2["filled"] == ["27478652"], str(sm2["filled"]))
check("rejections are separated from triggers",
      sm2["rejected"] == ["27478653"], str(sm2["rejected"]))

# an order that moves 32 -> 41 must be counted once, in its newest state
t._smart_reports = [{"row": x} for x in [
    ROW_6108, with_status(ROW_6108, "27478651", 41, "1000")]]
sm3 = t._smart_status_summary()
check("newest state wins: an order that moved 32 -> 41 is one order, counted as filled",
      len(sm3["orders"]) == 1 and sm3["by_status"] == {41: 1}
      and sm3["filled"] == ["27478651"], str(sm3))

print()
ok = all(results)
print(f"{sum(results)}/{len(results)} checks passed -> " + ("ALL OK" if ok else "FAILED"))
sys.exit(0 if ok else 1)
