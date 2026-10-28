"""Every way the feasibility report could report a PASS it has not earned.

  A) orders sent after the close            -> acceptance NOT TESTED
  B) same orders at 09:00:12, n=3           -> acceptance PASS, ack NOT TESTED (n<20)
  C) no strategy order, only an accepted canary -> acceptance NOT TESTED, canary
     check present and FAILING (no smart-report row)
  D) 25 strategy orders in session          -> both gates real
  E) 25 strategy orders, all rejected 924   -> acceptance NOT TESTED (the account
     refused before the accept path ran), and the canary being accepted must NOT
     rescue it. The account axis must say what to do about it.
  H) 5 refused 924 + 20 accepted            -> acceptance is measured on the 20
     the account was allowed to try, and the account axis still FAILS.
"""
import sys, warnings, logging, tempfile, json, datetime as dt
from pathlib import Path
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

# A real OnTSSmartStrategyReport row from 2026-10-28. The fixture used to pass
# the literal string "x" as a smart-report row, which the decoder correctly
# refused - and that refusal then showed up as a technical blocker, which is the
# right behaviour for a row that cannot be read. Using the real row makes the
# cases below exercise the decode path instead of fighting it.
SMART_ROW = ("27478651,TS,20261028,TSE,913R,0438724,0000000,11,6108,S,8,0,7,2,0,"
             "2026-10-28 13:37:42.000,34.1,1,32,,2026-10-28 13:37:42,"
             "[27478651][6108]msg,,,,0,0,,20,1,0,33.45,1,0,0,1,0,25.7,1,0,0,1,"
             "2026-10-29 13:20:00.000,1,0,0,0,0001-01-01 08:00:00.000,,[in], [out],")


def build(n_strategy, ack_code=0, at=(9, 0, 12), canary=False, smart_rows=0,
          qual_first=None):
    t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
    t.config = G.Config()
    t.config.log_dir = tempfile.mkdtemp()
    lg = logging.getLogger("t" + str(id(t)))
    lg.handlers = [logging.NullHandler()]
    lg.setLevel(logging.INFO)
    t.log = lg
    t.closed_trades = []
    t._smart_reports = [{"ts": 0.0, "row": SMART_ROW}] * smart_rows
    t.exec_stats = {"orders": [], "entry_slippage": []}
    ts = dt.datetime(*dt.date.today().timetuple()[:3], *at).timestamp()

    def add(i, code, is_canary):
        rec = {"symbol": str(1000 + i), "direction": "SHORT", "shares": 1000,
               "zhang": 1, "price": 50.0, "sl": 52.0, "tp": 48.0, "pos_pct": 0.25,
               "retries": 0, "ack_latency": 0.12, "ack_code": code, "msg": "",
               "submit_ts": ts, "canary": is_canary}
        if code == 924:
            # what the broker actually sends with a 924 (captured 2026-10-28)
            rec["msg"] = "924"
            rec["broker_msg"] = ("[924] 新增智慧條件單失敗,原因:"
                                 "投資人未具有上櫃股票當沖資格(無券當沖)")
        elif code:
            rec["msg"] = str(code)
            rec["broker_msg"] = f"[{code}] some other broker refusal"
        t.exec_stats["orders"].append(rec)

    for i in range(n_strategy):
        code = 924 if (qual_first is not None and i < qual_first) else ack_code
        add(i, code, False)
    if canary:
        add(999, 0, True)
    t._paper_report()
    out = Path(t.config.log_dir) / f"paper_report_{dt.datetime.now():%Y%m%d}.json"
    return json.loads(out.read_text(encoding="utf-8"))


def gate(rep, prefix):
    hits = {k: v for k, v in rep["checks"].items() if k.startswith(prefix)}
    return hits


results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"  [{'OK  ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail and not cond else ""))


print("A) 3 orders at 13:37 (after the close)")
a = build(3, at=(13, 37, 0))
check("A acceptance is NOT TESTED, not a pass",
      any("NOT TESTED" in k and v is False for k, v in gate(a, "order acceptance").items()),
      str(gate(a, "order acceptance")))

print("B) 3 orders at 09:00:12, in session, n=3")
b = build(3, at=(9, 0, 12))
check("B acceptance is a real PASS",
      gate(b, "order acceptance") == {"order acceptance 100%": True},
      str(gate(b, "order acceptance")))
check("B ack is NOT TESTED because n=3 < 20",
      any("NOT TESTED - n=3" in k and v is False for k, v in gate(b, "ack").items()),
      str(gate(b, "ack")))

print("C) no strategy order, only an accepted canary")
c = build(0, canary=True)
check("C acceptance is NOT TESTED (a canary cannot carry it)",
      any("no strategy order" in k and v is False for k, v in gate(c, "order acceptance").items()),
      str(gate(c, "order acceptance")))
check("C the canary gets its own check, and it FAILS without a smart-report row",
      gate(c, "canary") == {"canary: an accepted order produced a smart-report row": False},
      str(gate(c, "canary")))
check("C verdict is not-live-ready", c["verdict"] == "not-live-ready", c["verdict"])

print("D) 25 strategy orders in session")
d = build(25, at=(9, 0, 12))
check("D acceptance PASS", gate(d, "order acceptance") == {"order acceptance 100%": True},
      str(gate(d, "order acceptance")))
check("D ack gate is real at n=25",
      gate(d, "ack") == {"ack p90 < 2000ms": True}, str(gate(d, "ack")))

print("E) 25 strategy orders all rejected 924, canary accepted")
e = build(25, ack_code=924, at=(9, 0, 12), canary=True, smart_rows=1)
check("E acceptance is NOT TESTED, not a pass, even though the canary was accepted",
      any("NOT TESTED" in k and v is False for k, v in gate(e, "order acceptance").items()),
      str(gate(e, "order acceptance")))
check("E the account axis says the qualification is missing",
      gate(e, "account") == {"account: day-trade qualification held": False},
      str(gate(e, "account")))
check("E the blocker is filed under ACCOUNT, not under the integration",
      e["blocking_axis"] == "account" and not e["blockers_technical"],
      f'axis={e["blocking_axis"]} tech={e["blockers_technical"]}')
check("E the canary check passes on its own merits (order accepted + row received)",
      gate(e, "canary") == {"canary: an accepted order produced a smart-report row": True},
      str(gate(e, "canary")))
check("E the 924 qualification blocker is still named",
      any("當沖資格" in x or "qualification" in x for x in e["blockers"]), str(e["blockers"]))
check("E a real status row decodes, so no fake technical blocker appears",
      e["smart_order_rows_undecoded"] == 0 and len(e["smart_order_status"]) == 1
      and e["smart_order_status"][0]["status_text"] == "中台收單成功",
      str(e.get("smart_order_status")))

print("F) 25 strategy orders all rejected 924, in session, no canary")
f = build(25, ack_code=924, at=(9, 0, 12))
check("F acceptance is NOT TESTED - the account refused before the accept path ran",
      any("NOT TESTED" in k and v is False for k, v in gate(f, "order acceptance").items()),
      str(gate(f, "order acceptance")))
check("F ack is NOT TESTED - there is no accepted order to time",
      any("no accepted order to time" in k and v is False for k, v in gate(f, "ack").items()),
      str(gate(f, "ack")))
check("F the accept-path gap is filed as unmeasurable-via-account, not as a code finding",
      any("refused by the account" in x for x in f["unmeasurable_via_account"]),
      str(f["unmeasurable_via_account"]))
check("F no technical blocker is invented out of an account refusal",
      f["blocking_axis"] == "account" and not f["blockers_technical"],
      f'axis={f["blocking_axis"]} tech={f["blockers_technical"]}')

print("G) 25 rejected + an accepted canary: the canary ack must not time the accept path")
g = build(25, ack_code=924, at=(9, 0, 12), canary=True, smart_rows=1)
check("G ack is still NOT TESTED even though the canary was accepted",
      any("no accepted order to time" in k and v is False for k, v in gate(g, "ack").items()),
      str(gate(g, "ack")))
check("G acceptance is still NOT TESTED",
      any("NOT TESTED" in k and v is False for k, v in gate(g, "order acceptance").items()),
      str(gate(g, "order acceptance")))

print("H) 5 refused 924 + 20 accepted, in session")
h = build(25, at=(9, 0, 12), qual_first=5)
check("H acceptance is measured on the 20 the account was allowed to try",
      gate(h, "order acceptance") == {"order acceptance 100%": True},
      str(gate(h, "order acceptance")))
check("H the account axis still FAILS because 5 orders were refused",
      gate(h, "account") == {"account: day-trade qualification held": False},
      str(gate(h, "account")))
check("H the ack gate times only the accepted path",
      gate(h, "ack") == {"ack p90 < 2000ms": True}, str(gate(h, "ack")))

print()
ok = all(c for _, c, _ in results)
print(f"{sum(1 for _, c, _ in results if c)}/{len(results)} checks passed -> "
      + ("ALL OK" if ok else "FAILED"))
sys.exit(0 if ok else 1)
