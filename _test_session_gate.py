"""The acceptance gate must not pass on an after-hours order.

Measured 2026-10-28: a run started at 13:37 got ack_code 0 for every order, which
the old gate read as "order acceptance 100% PASS". Two cases:
  A) same orders, submitted after the close  -> must be NOT TESTED
  B) same orders, submitted at 09:00:12      -> must be a real PASS
"""
import sys, warnings, logging, tempfile, json, time, datetime as dt
from pathlib import Path
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G


def build(submit_ts_list, ack_code=0):
    t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
    t.config = G.Config()
    t.config.log_dir = tempfile.mkdtemp()
    lg = logging.getLogger("t" + str(id(t)))
    lg.handlers = [logging.StreamHandler(sys.stdout)]
    lg.setLevel(logging.INFO)
    t.log = lg
    t.closed_trades = []
    t.exec_stats = {"orders": [], "entry_slippage": []}
    for i, ts in enumerate(submit_ts_list):
        t.exec_stats["orders"].append({
            "symbol": str(1000 + i), "direction": "SHORT", "shares": 1000,
            "zhang": 1, "price": 50.0, "sl": 52.0, "tp": 48.0, "pos_pct": 0.25,
            "retries": 0, "ack_latency": 0.12, "ack_code": ack_code, "msg": "",
            "submit_ts": ts})
    t._paper_report()
    out = Path(t.config.log_dir) / f"paper_report_{dt.datetime.now():%Y%m%d}.json"
    return json.loads(out.read_text(encoding="utf-8"))


def _session_date():
    """The most recent weekday. These fixtures place orders inside 09:00-13:30,
    and _in_trading_session also rejects weekends, so a Saturday or Sunday
    `today` makes every order off-session and the gate cannot be exercised."""
    d = dt.date.today()
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def ts_at(hh, mm, ss):
    d = _session_date()
    return dt.datetime(d.year, d.month, d.day, hh, mm, ss).timestamp()


print("=" * 70)
print("CASE A - identical orders, sent at 13:37 (after the close)")
print("=" * 70)
a = build([ts_at(13, 37, 0), ts_at(13, 37, 1), ts_at(13, 37, 2)])
print()
print("=" * 70)
print("CASE B - identical orders, sent at 09:00:12 (in session)")
print("=" * 70)
b = build([ts_at(9, 0, 12), ts_at(9, 0, 13), ts_at(9, 0, 14)])

print()
print("=" * 70)
print("ASSERTIONS")
print("=" * 70)
ok = True
acc_a = [k for k in a["checks"] if k.startswith("order acceptance")]
acc_b = [k for k in b["checks"] if k.startswith("order acceptance")]
if len(acc_a) == 1 and "NOT TESTED" in acc_a[0] and a["checks"][acc_a[0]] is False:
    print("  A acceptance -> NOT TESTED, not counted as pass: OK")
else:
    print(f"  A acceptance -> {acc_a} {a['checks'][acc_a[0]]}: WRONG"); ok = False
if acc_b == ["order acceptance 100%"] and b["checks"][acc_b[0]] is True:
    print("  B acceptance -> real PASS in session: OK")
else:
    print(f"  B acceptance -> {acc_b} {b['checks'][acc_b[0]]}: WRONG"); ok = False
if any("outside 09:00-13:30" in x for x in a["blockers"]):
    print("  A blockers name the un-measurable window: OK")
else:
    print(f"  A blockers: {a['blockers']}: WRONG"); ok = False
if not any("outside 09:00-13:30" in x for x in b["blockers"]):
    print("  B blockers do NOT contain the session warning: OK")
else:
    print("  B polluted by the session warning: WRONG"); ok = False
ack_a = [k for k in a["checks"] if k.startswith("ack")]
if "NOT TESTED" in ack_a[0]:
    print("  A ack latency -> NOT TESTED too: OK")
else:
    print(f"  A ack -> {ack_a}: WRONG"); ok = False
print(f"  A verdict {a['verdict']} | B verdict {b['verdict']}")
print("ALL OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
